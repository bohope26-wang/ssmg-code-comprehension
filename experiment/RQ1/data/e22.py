def analyze_chat_moderation_queue(messages, user_history, policy):
    actions = []
    review_queue = []
    user_scores = defaultdict(int)
    keyword_rules = policy.get("keyword_rules", [])
    max_recent_flags = int(policy.get("max_recent_flags", 3))
    shadow_threshold = int(policy.get("shadow_threshold", 80))
    ban_threshold = int(policy.get("ban_threshold", 120))
    compiled_rules = []
    for rule in keyword_rules:
        try:
            compiled_rules.append(
                {
                    "name": rule.get("name", "unnamed"),
                    "pattern": re.compile(rule.get("pattern", ""), re.IGNORECASE),
                    "score": int(rule.get("score", 0) or 0),
                    "action": rule.get("action", "review"),
                }
            )
        except re.error:
            continue
    for user_id, history in (user_history or {}).items():
        recent_flags = int(history.get("recent_flags", 0) or 0)
        prior_bans = int(history.get("prior_bans", 0) or 0)
        user_scores[user_id] += recent_flags * 8 + prior_bans * 20
    for message in messages:
        message_id = message.get("id")
        user_id = message.get("user_id")
        text = str(message.get("text", "") or "")
        channel = message.get("channel", "general")
        action = {
            "message_id": message_id,
            "user_id": user_id,
            "channel": channel,
            "decision": "allow",
            "score": 0,
            "matches": [],
            "notes": [],
        }
        if not message_id or not user_id:
            action["decision"] = "reject"
            action["notes"].append("missing_identity")
            actions.append(action)
            continue
        if not text.strip():
            action["decision"] = "reject"
            action["notes"].append("empty_message")
            actions.append(action)
            continue
        normalized = re.sub(r"\s+", " ", text).strip()
        if len(normalized) > policy.get("max_length", 2000):
            action["score"] += 20
            action["notes"].append("too_long")
        if normalized.count("http://") + normalized.count("https://") > policy.get("max_links", 3):
            action["score"] += 25
            action["notes"].append("too_many_links")
        if sum(1 for ch in normalized if ch.isupper()) > len(normalized) * 0.7 and len(normalized) > 20:
            action["score"] += 10
            action["notes"].append("mostly_uppercase")
        for rule in compiled_rules:
            if rule["pattern"].search(normalized):
                action["score"] += rule["score"]
                action["matches"].append(rule["name"])
                if rule["action"] == "remove":
                    action["decision"] = "remove"
        history = user_history.get(user_id, {}) if user_history else {}
        recent_flags = int(history.get("recent_flags", 0) or 0)
        if recent_flags >= max_recent_flags:
            action["score"] += recent_flags * 5
            action["notes"].append("repeat_offender")
        if history.get("trusted"):
            action["score"] -= 15
            action["notes"].append("trusted_user")
        if channel in policy.get("strict_channels", []):
            action["score"] += 8
            action["notes"].append("strict_channel")
        user_scores[user_id] += max(0, action["score"])
        combined_score = action["score"] + user_scores[user_id]
        if action["decision"] == "remove":
            action["notes"].append("rule_forced_remove")
        elif combined_score >= ban_threshold:
            action["decision"] = "ban_review"
            action["notes"].append("ban_threshold")
        elif combined_score >= shadow_threshold:
            action["decision"] = "shadow_review"
            action["notes"].append("shadow_threshold")
        elif action["score"] >= policy.get("review_threshold", 40):
            action["decision"] = "review"
        else:
            action["decision"] = "allow"
        if action["decision"] in {"review", "shadow_review", "ban_review"}:
            priority = combined_score
            if "strict_channel" in action["notes"]:
                priority += 10
            review_queue.append({"message_id": message_id, "priority": priority, "decision": action["decision"]})
        actions.append(action)
    review_queue.sort(key=lambda row: (-row["priority"], row["message_id"]))
    summary = {
        "allowed": sum(1 for item in actions if item["decision"] == "allow"),
        "rejected": sum(1 for item in actions if item["decision"] == "reject"),
        "removed": sum(1 for item in actions if item["decision"] == "remove"),
        "review": len(review_queue),
    }
    return {"actions": actions, "review_queue": review_queue, "user_scores": dict(user_scores), "summary": summary}