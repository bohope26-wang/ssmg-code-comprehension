def route_support_ticket(ticket, agents, now_hour):
    if not agents:
        return {"agent_id": None, "reason": "no_agents_available", "score": 0}

    product = ticket.get("product")
    severity = ticket.get("severity", "normal")
    language = ticket.get("language", "en")
    customer_tier = ticket.get("customer_tier", "standard")

    best_agent = None
    best_score = -1
    best_notes = []

    for agent in agents:
        if not agent.get("active", True):
            continue
        if now_hour not in agent.get("working_hours", range(24)):
            continue

        score = 10
        notes = []
        queue_size = int(agent.get("open_tickets", 0) or 0)

        if product in agent.get("products", []):
            score += 30
            notes.append("product_match")
        if language in agent.get("languages", []):
            score += 15
            notes.append("language_match")
        if severity == "critical" and agent.get("tier") == "senior":
            score += 25
            notes.append("critical_senior")
        if customer_tier in ("gold", "enterprise") and agent.get("vip_enabled"):
            score += 20
            notes.append("vip_enabled")

        score -= min(queue_size * 4, 30)
        if agent.get("on_call"):
            score += 8
        if ticket.get("region") and ticket.get("region") != agent.get("region"):
            score -= 5

        if score > best_score:
            best_agent = agent
            best_score = score
            best_notes = notes

    if best_agent is None:
        return {"agent_id": None, "reason": "no_shift_match", "score": 0}

    reason = ",".join(best_notes) if best_notes else "least_loaded_general_match"
    return {"agent_id": best_agent.get("id"), "reason": reason, "score": best_score}