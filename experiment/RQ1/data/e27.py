def evaluate_network_change_request(change_request, current_rules, asset_inventory, security_policy):
    findings = []
    approved_rules = []
    blocked_rules = []
    review_items = []
    asset_index = {asset["id"]: asset for asset in asset_inventory if asset.get("id")}
    zone_by_cidr = {}
    risky_ports = set(security_policy.get("risky_ports", [22, 3389, 445, 1433]))
    forbidden_zones = set(security_policy.get("forbidden_zones", []))
    max_expiry_days = int(security_policy.get("max_expiry_days", 90))
    for asset in asset_inventory:
        cidr = asset.get("cidr")
        if cidr:
            zone_by_cidr[cidr] = asset.get("zone", "unknown")
    requester = change_request.get("requester")
    business_justification = str(change_request.get("justification", "")).strip()
    emergency = bool(change_request.get("emergency"))
    if not requester:
        findings.append({"severity": "high", "reason": "missing_requester"})
    if len(business_justification) < security_policy.get("minimum_justification_length", 20):
        findings.append({"severity": "medium", "reason": "weak_business_justification"})
    try:
        requested_at = datetime.fromisoformat(str(change_request.get("requested_at")))
    except (TypeError, ValueError):
        requested_at = datetime.utcnow()
        findings.append({"severity": "low", "reason": "request_time_defaulted"})
    for index, rule in enumerate(change_request.get("rules", []), start=1):
        action = rule.get("action", "allow")
        protocol = str(rule.get("protocol", "tcp")).lower()
        source = rule.get("source")
        destination = rule.get("destination")
        ports = rule.get("ports", [])
        expiry = rule.get("expires_at")
        rule_findings = []
        status = "approve"
        if action not in {"allow", "deny"}:
            status = "block"
            rule_findings.append("invalid_action")
        if protocol not in {"tcp", "udp", "icmp"}:
            status = "block"
            rule_findings.append("invalid_protocol")
        if not source or not destination:
            status = "block"
            rule_findings.append("missing_endpoint")
        if protocol == "icmp" and ports:
            rule_findings.append("icmp_ports_ignored")
            ports = []
        if protocol in {"tcp", "udp"} and not ports:
            status = "block"
            rule_findings.append("missing_ports")
        normalized_ports = []
        for port in ports:
            if isinstance(port, str) and "-" in port:
                left, right = port.split("-", 1)
                try:
                    start = int(left)
                    end = int(right)
                except ValueError:
                    status = "block"
                    rule_findings.append("invalid_port_range")
                    continue
                if start > end or start < 1 or end > 65535:
                    status = "block"
                    rule_findings.append("port_range_out_of_bounds")
                    continue
                normalized_ports.extend(range(start, min(end, start + security_policy.get("max_expanded_ports", 50)) + 1))
                if end - start + 1 > security_policy.get("max_expanded_ports", 50):
                    rule_findings.append("large_port_range_truncated_for_review")
            else:
                try:
                    value = int(port)
                except (TypeError, ValueError):
                    status = "block"
                    rule_findings.append("invalid_port")
                    continue
                if value < 1 or value > 65535:
                    status = "block"
                    rule_findings.append("port_out_of_bounds")
                    continue
                normalized_ports.append(value)
        source_asset = asset_index.get(source)
        destination_asset = asset_index.get(destination)
        source_zone = source_asset.get("zone") if source_asset else zone_by_cidr.get(source, "external")
        destination_zone = destination_asset.get("zone") if destination_asset else zone_by_cidr.get(destination, "external")
        if destination_zone in forbidden_zones and action == "allow":
            status = "block"
            rule_findings.append("destination_zone_forbidden")
        if source_zone == "external" and destination_zone in security_policy.get("internal_zones", []):
            rule_findings.append("external_to_internal")
            if not emergency:
                status = "review" if status != "block" else status
        if set(normalized_ports) & risky_ports and action == "allow":
            rule_findings.append("risky_port")
            status = "review" if status != "block" else status
        if expiry:
            try:
                expiry_date = datetime.fromisoformat(str(expiry))
                if (expiry_date - requested_at).days > max_expiry_days:
                    rule_findings.append("expiry_too_long")
                    status = "review" if status != "block" else status
                if expiry_date < requested_at:
                    status = "block"
                    rule_findings.append("expiry_in_past")
            except ValueError:
                status = "block"
                rule_findings.append("invalid_expiry")
        elif action == "allow" and not emergency:
            rule_findings.append("missing_expiry")
            status = "review" if status != "block" else status
        duplicate = False
        for existing in current_rules:
            if existing.get("source") == source and existing.get("destination") == destination:
                existing_ports = set(existing.get("ports", []))
                if existing.get("protocol", "tcp") == protocol and set(normalized_ports).issubset(existing_ports):
                    duplicate = True
                    break
        if duplicate:
            rule_findings.append("duplicate_existing_rule")
            status = "review" if status == "approve" else status
        result = {
            "index": index,
            "action": action,
            "protocol": protocol,
            "source": source,
            "destination": destination,
            "source_zone": source_zone,
            "destination_zone": destination_zone,
            "ports": sorted(set(normalized_ports)),
            "findings": sorted(set(rule_findings)),
        }
        if status == "approve":
            approved_rules.append(result)
        elif status == "block":
            blocked_rules.append(result)
        else:
            review_items.append(result)
    high_findings = sum(1 for item in findings if item["severity"] == "high")
    if blocked_rules or high_findings:
        overall = "blocked"
    elif review_items or findings:
        overall = "needs_review"
    else:
        overall = "approved"
    return {
        "status": overall,
        "approved_rules": approved_rules,
        "review_items": review_items,
        "blocked_rules": blocked_rules,
        "request_findings": findings,
        "summary": {
            "approved": len(approved_rules),
            "review": len(review_items),
            "blocked": len(blocked_rules),
        },
    }
