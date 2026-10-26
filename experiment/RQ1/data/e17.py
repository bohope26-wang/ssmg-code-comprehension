def process_iot_alert_stream(devices, events, rules, maintenance_windows):
    device_state = {}
    alerts = []
    suppressed = []
    counters = defaultdict(int)
    rule_index = {rule["name"]: rule for rule in rules if rule.get("name")}
    for device in devices:
        device_id = device.get("id")
        if not device_id:
            continue
        device_state[device_id] = {
            "type": device.get("type", "unknown"),
            "site": device.get("site", "default"),
            "last_seen": None,
            "last_values": {},
            "open_alerts": set(),
            "health": "unknown",
        }
    def parse_time(value):
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))
    parsed_windows = []
    for window in maintenance_windows or []:
        try:
            parsed_windows.append(
                {
                    "site": window.get("site"),
                    "device_id": window.get("device_id"),
                    "start": parse_time(window["start"]),
                    "end": parse_time(window["end"]),
                    "reason": window.get("reason", "maintenance"),
                }
            )
        except (KeyError, ValueError):
            counters["invalid_maintenance_window"] += 1
    def in_maintenance(device_id, site, timestamp):
        for window in parsed_windows:
            if window["device_id"] not in (None, device_id):
                continue
            if window["site"] not in (None, site):
                continue
            if window["start"] <= timestamp <= window["end"]:
                return window["reason"]
        return None
    sorted_events = []
    for event in events:
        try:
            event_copy = dict(event)
            event_copy["timestamp"] = parse_time(event["timestamp"])
            sorted_events.append(event_copy)
        except (KeyError, ValueError, TypeError):
            counters["invalid_event"] += 1
    sorted_events.sort(key=lambda row: (row["timestamp"], row.get("device_id", "")))
    for event in sorted_events:
        device_id = event.get("device_id")
        metric = event.get("metric")
        value = event.get("value")
        timestamp = event["timestamp"]
        if device_id not in device_state:
            counters["unknown_device"] += 1
            continue
        if metric is None:
            counters["missing_metric"] += 1
            continue
        state = device_state[device_id]
        state["last_seen"] = timestamp
        site = state["site"]
        maintenance_reason = in_maintenance(device_id, site, timestamp)
        if event.get("kind") == "heartbeat":
            state["health"] = "online"
            counters["heartbeat"] += 1
            continue
        if event.get("kind") == "offline":
            state["health"] = "offline"
            alert_key = f"{device_id}:offline"
            if alert_key not in state["open_alerts"]:
                alert = {"device_id": device_id, "metric": "offline", "severity": "high", "time": timestamp.isoformat()}
                if maintenance_reason:
                    suppressed.append({**alert, "reason": maintenance_reason})
                else:
                    alerts.append(alert)
                    state["open_alerts"].add(alert_key)
            continue
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            counters["non_numeric_value"] += 1
            continue
        previous = state["last_values"].get(metric)
        state["last_values"][metric] = numeric_value
        for rule_name, rule in rule_index.items():
            if rule.get("device_type") not in (None, state["type"]):
                continue
            if rule.get("metric") != metric:
                continue
            severity = rule.get("severity", "medium")
            direction = rule.get("direction", "above")
            threshold = float(rule.get("threshold", 0) or 0)
            hysteresis = float(rule.get("hysteresis", 0) or 0)
            triggered = False
            recovered = False
            if direction == "above":
                triggered = numeric_value > threshold
                recovered = numeric_value < threshold - hysteresis
            elif direction == "below":
                triggered = numeric_value < threshold
                recovered = numeric_value > threshold + hysteresis
            elif direction == "jump" and previous is not None:
                triggered = abs(numeric_value - previous) >= threshold
            alert_key = f"{device_id}:{rule_name}"
            if triggered and alert_key not in state["open_alerts"]:
                alert = {
                    "device_id": device_id,
                    "metric": metric,
                    "rule": rule_name,
                    "severity": severity,
                    "value": numeric_value,
                    "time": timestamp.isoformat(),
                }
                if maintenance_reason:
                    suppressed.append({**alert, "reason": maintenance_reason})
                else:
                    alerts.append(alert)
                    state["open_alerts"].add(alert_key)
            elif recovered and alert_key in state["open_alerts"]:
                state["open_alerts"].remove(alert_key)
                counters["recovered_alert"] += 1
    summary = {
        "devices_seen": sum(1 for state in device_state.values() if state["last_seen"] is not None),
        "open_alerts": sum(len(state["open_alerts"]) for state in device_state.values()),
        "counters": dict(counters),
    }
    return {"alerts": alerts, "suppressed": suppressed, "device_state": device_state, "summary": summary}