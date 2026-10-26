def score_grant_applications(applications, reviewers, budget, scoring_rules):
    results = []
    reviewer_load = {reviewer["id"]: 0 for reviewer in reviewers if reviewer.get("id")}
    reviewer_index = {reviewer["id"]: reviewer for reviewer in reviewers if reviewer.get("id")}
    remaining_budget = float(budget)
    conflicts = []
    required_sections = scoring_rules.get("required_sections", ["abstract", "budget", "impact"])
    category_weights = scoring_rules.get("category_weights", {})
    minimum_score = float(scoring_rules.get("minimum_score", 70))
    max_reviewers = int(scoring_rules.get("reviewers_per_application", 2))

    def reviewer_score(reviewer, application):
        expertise = set(reviewer.get("expertise", []))
        topics = set(application.get("topics", []))
        if application.get("organization") in reviewer.get("conflicts", []):
            return None
        score = len(expertise & topics) * 10
        score -= reviewer_load.get(reviewer["id"], 0) * 3
        if reviewer.get("region") == application.get("region"):
            score += 2
        if reviewer.get("senior"):
            score += 1
        return score
    prepared = []
    for app in applications:
        app_id = app.get("id")
        missing = [name for name in required_sections if not app.get(name)]
        requested = float(app.get("requested_budget", 0) or 0)
        if not app_id:
            conflicts.append({"id": None, "reason": "missing_application_id"})
            continue
        if missing:
            results.append({"id": app_id, "status": "ineligible", "reason": "missing_sections", "missing": missing})
            continue
        if requested <= 0:
            results.append({"id": app_id, "status": "ineligible", "reason": "invalid_budget"})
            continue
        base_score = 0.0
        score_breakdown = {}
        for category, weight in category_weights.items():
            raw = float(app.get("scores", {}).get(category, 0) or 0)
            weighted = raw * float(weight)
            score_breakdown[category] = round(weighted, 2)
            base_score += weighted
        if app.get("early_career"):
            base_score += scoring_rules.get("early_career_bonus", 0)
            score_breakdown["early_career_bonus"] = scoring_rules.get("early_career_bonus", 0)
        if app.get("previous_award") and not scoring_rules.get("allow_repeat_awards", True):
            base_score -= scoring_rules.get("repeat_award_penalty", 10)
            score_breakdown["repeat_award_penalty"] = -scoring_rules.get("repeat_award_penalty", 10)
        prepared.append(
            {
                "id": app_id,
                "requested": requested,
                "score": round(base_score, 2),
                "breakdown": score_breakdown,
                "application": app,
            }
        )
    for item in prepared:
        candidates = []
        for reviewer_id, reviewer in reviewer_index.items():
            score = reviewer_score(reviewer, item["application"])
            if score is None:
                continue
            candidates.append((score, reviewer_id))
        candidates.sort(reverse=True)
        assigned = []
        for _, reviewer_id in candidates:
            if len(assigned) >= max_reviewers:
                break
            assigned.append(reviewer_id)
            reviewer_load[reviewer_id] += 1
        if len(assigned) < max_reviewers:
            conflicts.append({"id": item["id"], "reason": "not_enough_reviewers", "assigned": assigned})
        item["reviewers"] = assigned
    prepared.sort(key=lambda row: (-row["score"], row["requested"], row["id"]))
    for item in prepared:
        if item["score"] < minimum_score:
            results.append(
                {
                    "id": item["id"],
                    "status": "decline",
                    "score": item["score"],
                    "reviewers": item.get("reviewers", []),
                    "reason": "below_minimum_score",
                }
            )
            continue
        if item["requested"] <= remaining_budget:
            award = item["requested"]
            remaining_budget -= award
            status = "fund"
        elif remaining_budget >= item["requested"] * scoring_rules.get("partial_min_fraction", 0.5):
            award = remaining_budget
            remaining_budget = 0
            status = "partial_fund"
        else:
            award = 0
            status = "waitlist"
        results.append(
            {
                "id": item["id"],
                "status": status,
                "score": item["score"],
                "award": round(award, 2),
                "requested": round(item["requested"], 2),
                "reviewers": item.get("reviewers", []),
                "breakdown": item["breakdown"],
            }
        )
    summary = {
        "funded": sum(1 for row in results if row.get("status") in {"fund", "partial_fund"}),
        "declined": sum(1 for row in results if row.get("status") == "decline"),
        "ineligible": sum(1 for row in results if row.get("status") == "ineligible"),
        "remaining_budget": round(remaining_budget, 2),
        "reviewer_load": reviewer_load,
    }
    return {"results": results, "conflicts": conflicts, "summary": summary}
