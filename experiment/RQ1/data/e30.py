def audit_degree_completion(student_record, program_requirements, course_catalog):
    completed_courses = []
    rejected_courses = []
    requirement_results = []
    used_courses = set()
    warnings = []
    total_credits = 0.0
    quality_points = 0.0
    residency_credits = 0.0
    repeated_best = {}
    grade_points = program_requirements.get(
        "grade_points",
        {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0, "P": None},
    )
    for attempt in student_record.get("courses", []):
        code = str(attempt.get("code", "")).strip().upper()
        grade = str(attempt.get("grade", "")).strip().upper()
        term = str(attempt.get("term", "")).strip()
        credits = float(attempt.get("credits", course_catalog.get(code, {}).get("credits", 0)) or 0)
        if not code or code not in course_catalog:
            rejected_courses.append({"code": code, "term": term, "reason": "unknown_course"})
            continue
        if grade not in grade_points:
            rejected_courses.append({"code": code, "term": term, "reason": "unknown_grade"})
            continue
        if credits <= 0:
            rejected_courses.append({"code": code, "term": term, "reason": "invalid_credits"})
            continue
        points = grade_points[grade]
        passed = grade == "P" or (points is not None and points >= program_requirements.get("minimum_passing_points", 1.0))
        normalized = {
            "code": code,
            "grade": grade,
            "term": term,
            "credits": credits,
            "points": points,
            "passed": passed,
            "institution": attempt.get("institution", student_record.get("home_institution")),
            "level": course_catalog[code].get("level", 100),
            "tags": set(course_catalog[code].get("tags", [])),
        }
        completed_courses.append(normalized)
        previous = repeated_best.get(code)
        if previous is None:
            repeated_best[code] = normalized
        else:
            previous_points = -1 if previous["points"] is None else previous["points"]
            current_points = -1 if normalized["points"] is None else normalized["points"]
            if current_points > previous_points:
                repeated_best[code] = normalized
    counted_courses = list(repeated_best.values())
    for course in counted_courses:
        if not course["passed"]:
            continue
        total_credits += course["credits"]
        if course["institution"] == student_record.get("home_institution"):
            residency_credits += course["credits"]
        if course["points"] is not None:
            quality_points += course["points"] * course["credits"]
    gpa_credits = sum(course["credits"] for course in counted_courses if course["points"] is not None)
    gpa = quality_points / gpa_credits if gpa_credits else 0.0
    if completed_courses and len(completed_courses) != len(counted_courses):
        warnings.append("repeated_courses_collapsed_to_best_attempt")
    substitutions = {}
    for item in student_record.get("substitutions", []):
        target = str(item.get("target", "")).strip().upper()
        source = str(item.get("source", "")).strip().upper()
        if target and source:
            substitutions.setdefault(target, set()).add(source)
    for group in program_requirements.get("groups", []):
        group_id = group.get("id")
        required_credits = float(group.get("credits", 0) or 0)
        required_count = int(group.get("count", 0) or 0)
        allowed_codes = {str(code).upper() for code in group.get("courses", [])}
        allowed_tags = set(group.get("tags", []))
        min_level = int(group.get("min_level", 0) or 0)
        allow_reuse = bool(group.get("allow_reuse", False))
        group_courses = []
        group_credits = 0.0
        for course in counted_courses:
            if not course["passed"]:
                continue
            if not allow_reuse and course["code"] in used_courses:
                continue
            code_match = course["code"] in allowed_codes
            tag_match = bool(course["tags"] & allowed_tags)
            substitution_match = course["code"] in substitutions.get(group_id, set())
            if not code_match and not tag_match and not substitution_match:
                continue
            if course["level"] < min_level:
                continue
            group_courses.append(course)
            group_credits += course["credits"]
            if not allow_reuse:
                used_courses.add(course["code"])
            if required_count and len(group_courses) >= required_count:
                break
            if required_credits and group_credits >= required_credits:
                break
        satisfied = True
        reasons = []
        if required_count and len(group_courses) < required_count:
            satisfied = False
            reasons.append("course_count_shortfall")
        if required_credits and group_credits < required_credits:
            satisfied = False
            reasons.append("credit_shortfall")
        requirement_results.append(
            {
                "group": group_id,
                "satisfied": satisfied,
                "credits": round(group_credits, 2),
                "courses": [course["code"] for course in group_courses],
                "reasons": reasons,
            }
        )
    status = "complete"
    global_reasons = []
    if total_credits < program_requirements.get("minimum_total_credits", 0):
        status = "incomplete"
        global_reasons.append("total_credit_shortfall")
    if residency_credits < program_requirements.get("minimum_residency_credits", 0):
        status = "incomplete"
        global_reasons.append("residency_credit_shortfall")
    if gpa < program_requirements.get("minimum_gpa", 0):
        status = "incomplete"
        global_reasons.append("gpa_below_minimum")
    if any(not item["satisfied"] for item in requirement_results):
        status = "incomplete"
        global_reasons.append("unsatisfied_requirement_group")
    return {
        "student_id": student_record.get("id"),
        "status": status,
        "gpa": round(gpa, 3),
        "total_credits": round(total_credits, 2),
        "residency_credits": round(residency_credits, 2),
        "requirements": requirement_results,
        "rejected_courses": rejected_courses,
        "warnings": warnings,
        "reasons": sorted(set(global_reasons)),
    }