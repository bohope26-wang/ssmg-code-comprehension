def audit_loan_application(application, bureau_report, policy):
    decision = {
        "status": "review",
        "reasons": [],
        "risk_score": 0,
        "conditions": [],
        "verified_fields": {},
        "pricing": {},
    }
    applicant = application.get("applicant", {}) or {}
    requested = float(application.get("amount", 0) or 0)
    term_months = int(application.get("term_months", 0) or 0)
    product = application.get("product", "personal")
    if requested <= 0:
        decision["status"] = "reject"
        decision["reasons"].append("invalid_amount")
    if term_months <= 0:
        decision["status"] = "reject"
        decision["reasons"].append("invalid_term")
    if product not in policy.get("products", {}):
        decision["status"] = "reject"
        decision["reasons"].append("unsupported_product")
    age = int(applicant.get("age", 0) or 0)
    income = float(applicant.get("monthly_income", 0) or 0)
    employment_months = int(applicant.get("employment_months", 0) or 0)
    existing_debt = float(bureau_report.get("monthly_debt", 0) or 0)
    credit_score = int(bureau_report.get("score", 0) or 0)
    delinquencies = int(bureau_report.get("delinquencies_24m", 0) or 0)
    decision["verified_fields"]["identity"] = bool(applicant.get("government_id"))
    decision["verified_fields"]["income"] = income > 0 and bool(applicant.get("income_document"))
    decision["verified_fields"]["bureau"] = bureau_report.get("matched_ssn") is True
    if age < policy.get("minimum_age", 18):
        decision["status"] = "reject"
        decision["reasons"].append("under_minimum_age")
    if not decision["verified_fields"]["identity"]:
        decision["conditions"].append("provide_government_id")
    if not decision["verified_fields"]["income"]:
        decision["conditions"].append("provide_income_documentation")
    if not decision["verified_fields"]["bureau"]:
        decision["conditions"].append("resolve_bureau_identity_mismatch")
    product_policy = policy.get("products", {}).get(product, {})
    max_amount = float(product_policy.get("max_amount", math.inf))
    min_score = int(product_policy.get("min_score", 0))
    max_dti = float(product_policy.get("max_dti", 1.0))
    base_rate = float(product_policy.get("base_rate", 0.12))
    if requested > max_amount:
        decision["status"] = "reject"
        decision["reasons"].append("amount_above_product_limit")
    if credit_score and credit_score < min_score:
        decision["status"] = "reject"
        decision["reasons"].append("credit_score_below_minimum")
    if delinquencies >= product_policy.get("max_delinquencies", 3):
        decision["status"] = "reject"
        decision["reasons"].append("recent_delinquency_limit")
    estimated_payment = requested / max(term_months, 1)
    debt_to_income = (existing_debt + estimated_payment) / income if income > 0 else math.inf
    decision["verified_fields"]["dti"] = round(debt_to_income, 4) if math.isfinite(debt_to_income) else None
    if debt_to_income > max_dti:
        decision["status"] = "reject"
        decision["reasons"].append("debt_to_income_too_high")
    risk_score = 50
    if credit_score >= 760:
        risk_score -= 18
    elif credit_score >= 700:
        risk_score -= 10
    elif credit_score >= 640:
        risk_score += 4
    else:
        risk_score += 18
    if employment_months < 6:
        risk_score += 12
        decision["conditions"].append("employment_stability_review")
    elif employment_months > 36:
        risk_score -= 6
    if debt_to_income > max_dti * 0.85:
        risk_score += 10
    if delinquencies:
        risk_score += delinquencies * 6
    if applicant.get("self_employed"):
        risk_score += 6
        decision["conditions"].append("business_income_review")
    collateral = application.get("collateral") or {}
    if collateral:
        collateral_value = float(collateral.get("value", 0) or 0)
        lien_count = int(collateral.get("liens", 0) or 0)
        loan_to_value = requested / collateral_value if collateral_value > 0 else math.inf
        decision["verified_fields"]["ltv"] = round(loan_to_value, 4) if math.isfinite(loan_to_value) else None
        if lien_count:
            risk_score += 10
            decision["conditions"].append("clear_collateral_lien")
        if loan_to_value <= product_policy.get("preferred_ltv", 0.7):
            risk_score -= 8
        elif loan_to_value > product_policy.get("max_ltv", 0.9):
            decision["status"] = "reject"
            decision["reasons"].append("loan_to_value_too_high")
    elif product_policy.get("requires_collateral"):
        decision["status"] = "reject"
        decision["reasons"].append("missing_collateral")
    rate_adjustment = max(-0.02, min(0.08, (risk_score - 45) / 1000))
    final_rate = max(product_policy.get("floor_rate", 0.03), base_rate + rate_adjustment)
    decision["pricing"] = {
        "rate": round(final_rate, 4),
        "estimated_monthly_payment": round(estimated_payment * (1 + final_rate / 12), 2),
    }
    decision["risk_score"] = max(0, min(100, int(round(risk_score))))
    if decision["status"] != "reject":
        if decision["risk_score"] >= product_policy.get("manual_review_score", 65):
            decision["status"] = "manual_review"
            decision["reasons"].append("risk_score_requires_review")
        elif decision["conditions"]:
            decision["status"] = "conditional_approval"
        else:
            decision["status"] = "approved"
    decision["conditions"] = sorted(set(decision["conditions"]))
    decision["reasons"] = sorted(set(decision["reasons"]))
    return decision
