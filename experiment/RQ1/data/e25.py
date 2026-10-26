def adjudicate_insurance_claim_batch(claims, member_profiles, coverage_rules, provider_contracts):
    decisions = []
    batch_warnings = []
    member_index = {member["id"]: member for member in member_profiles if member.get("id")}
    contract_index = {contract["provider_id"]: contract for contract in provider_contracts if contract.get("provider_id")}
    plan_rules = {rule["plan"]: rule for rule in coverage_rules if rule.get("plan")}
    batch_totals = {
        "submitted": 0.0,
        "allowed": 0.0,
        "member_responsibility": 0.0,
        "payable": 0.0,
        "denied": 0,
        "pended": 0,
    }
    for claim in claims:
        claim_id = claim.get("id")
        member_id = claim.get("member_id")
        provider_id = claim.get("provider_id")
        service_date_raw = claim.get("service_date")
        submitted_total = 0.0
        allowed_total = 0.0
        member_total = 0.0
        payable_total = 0.0
        line_results = []
        reasons = []
        flags = []
        status = "pay"
        if not claim_id:
            claim_id = f"claim-{len(decisions) + 1}"
            flags.append("generated_claim_id")
        if not member_id or member_id not in member_index:
            status = "deny"
            reasons.append("unknown_member")
        if not provider_id or provider_id not in contract_index:
            status = "pend" if status != "deny" else status
            reasons.append("unknown_or_uncontracted_provider")
        try:
            service_date = datetime.fromisoformat(str(service_date_raw)).date()
        except (TypeError, ValueError):
            service_date = None
            status = "deny"
            reasons.append("invalid_service_date")
        member = member_index.get(member_id, {})
        contract = contract_index.get(provider_id, {})
        plan_name = member.get("plan")
        plan = plan_rules.get(plan_name, {})
        if member and not plan:
            status = "pend" if status != "deny" else status
            reasons.append("missing_plan_rules")
        if member and service_date:
            effective = member.get("effective_date")
            terminated = member.get("terminated_date")
            try:
                effective_date = datetime.fromisoformat(str(effective)).date() if effective else None
                terminated_date = datetime.fromisoformat(str(terminated)).date() if terminated else None
            except ValueError:
                effective_date = None
                terminated_date = None
                flags.append("bad_member_date")
            if effective_date and service_date < effective_date:
                status = "deny"
                reasons.append("before_coverage_effective_date")
            if terminated_date and service_date > terminated_date:
                status = "deny"
                reasons.append("after_coverage_termination")
        deductible_remaining = float(member.get("deductible_remaining", 0) or 0)
        out_of_pocket_remaining = float(member.get("oop_remaining", math.inf))
        network_multiplier = float(contract.get("allowed_multiplier", 1.0) or 1.0)
        line_items = claim.get("lines", []) or []
        if not line_items:
            status = "deny"
            reasons.append("empty_claim")
        for index, line in enumerate(line_items, start=1):
            procedure = str(line.get("procedure", "")).strip()
            diagnosis = str(line.get("diagnosis", "")).strip()
            units = int(line.get("units", 1) or 1)
            charge = float(line.get("charge", 0) or 0)
            modifiers = set(line.get("modifiers", []) or [])
            line_status = "pay"
            line_reason = []
            submitted_total += max(0.0, charge)
            if not procedure:
                line_status = "deny"
                line_reason.append("missing_procedure")
            if not diagnosis:
                line_status = "pend" if line_status != "deny" else line_status
                line_reason.append("missing_diagnosis")
            if units <= 0 or charge <= 0:
                line_status = "deny"
                line_reason.append("invalid_units_or_charge")
            excluded = set(plan.get("excluded_procedures", []))
            prior_auth = set(plan.get("prior_auth_required", []))
            preventive = set(plan.get("preventive_procedures", []))
            if procedure in excluded:
                line_status = "deny"
                line_reason.append("procedure_excluded")
            if procedure in prior_auth and not line.get("authorization_id"):
                line_status = "pend" if line_status != "deny" else line_status
                line_reason.append("missing_prior_authorization")
            if "experimental" in modifiers and not plan.get("covers_experimental"):
                line_status = "deny"
                line_reason.append("experimental_not_covered")
            contracted_rate = contract.get("rates", {}).get(procedure)
            if contracted_rate is None:
                contracted_rate = plan.get("default_allowed", charge * network_multiplier)
                flags.append(f"line_{index}_default_rate")
            allowed = min(charge, float(contracted_rate) * max(1, units))
            copay = 0.0
            coinsurance = float(plan.get("coinsurance", 0.2))
            if procedure in preventive:
                deductible_applied = 0.0
                member_share = 0.0
            else:
                deductible_applied = min(deductible_remaining, allowed)
                deductible_remaining -= deductible_applied
                remaining_allowed = max(0.0, allowed - deductible_applied)
                copay = float(plan.get("copay_by_procedure", {}).get(procedure, plan.get("default_copay", 0)) or 0)
                member_share = deductible_applied + copay + remaining_allowed * coinsurance
            member_share = min(member_share, out_of_pocket_remaining)
            out_of_pocket_remaining = max(0.0, out_of_pocket_remaining - member_share)
            payable = max(0.0, allowed - member_share)
            if line_status == "deny":
                allowed = 0.0
                member_share = 0.0
                payable = 0.0
            elif line_status == "pend":
                payable = 0.0
            allowed_total += allowed
            member_total += member_share
            payable_total += payable
            line_results.append(
                {
                    "line": index,
                    "procedure": procedure,
                    "status": line_status,
                    "allowed": round(allowed, 2),
                    "member_responsibility": round(member_share, 2),
                    "payable": round(payable, 2),
                    "reasons": line_reason,
                }
            )
        if any(line["status"] == "deny" for line in line_results) and all(line["status"] == "deny" for line in line_results):
            status = "deny"
        elif any(line["status"] == "pend" for line in line_results) and status == "pay":
            status = "pend"
        if payable_total > plan.get("single_claim_review_threshold", math.inf):
            status = "pend" if status != "deny" else status
            reasons.append("large_claim_manual_review")
        if submitted_total > allowed_total * 3 and allowed_total > 0:
            flags.append("high_charge_to_allowed_ratio")
        batch_totals["submitted"] += submitted_total
        batch_totals["allowed"] += allowed_total
        batch_totals["member_responsibility"] += member_total
        batch_totals["payable"] += payable_total
        if status == "deny":
            batch_totals["denied"] += 1
        if status == "pend":
            batch_totals["pended"] += 1
        decisions.append(
            {
                "claim_id": claim_id,
                "status": status,
                "member_id": member_id,
                "provider_id": provider_id,
                "submitted": round(submitted_total, 2),
                "allowed": round(allowed_total, 2),
                "member_responsibility": round(member_total, 2),
                "payable": round(payable_total, 2),
                "reasons": sorted(set(reasons)),
                "flags": sorted(set(flags)),
                "lines": line_results,
            }
        )
    if batch_totals["submitted"] and batch_totals["payable"] / batch_totals["submitted"] < 0.2:
        batch_warnings.append("low_batch_payment_ratio")
    batch_totals = {key: round(value, 2) if isinstance(value, float) else value for key, value in batch_totals.items()}
    return {"decisions": decisions, "batch_totals": batch_totals, "warnings": batch_warnings}