def evaluate_password_policy(password, user_profile, history):
    violations = []
    score = 0
    if len(password) < 12:
        violations.append("too_short")
    else:
        score += 2
    checks = {
        "uppercase": any(ch.isupper() for ch in password),
        "lowercase": any(ch.islower() for ch in password),
        "digit": any(ch.isdigit() for ch in password),
        "symbol": any(not ch.isalnum() for ch in password),
    }
    for name, passed in checks.items():
        if passed:
            score += 1
        else:
            violations.append(f"missing_{name}")
    normalized = password.lower()
    forbidden_tokens = [
        str(user_profile.get("username", "")).lower(),
        str(user_profile.get("email", "")).split("@")[0].lower(),
        str(user_profile.get("department", "")).lower(),
    ]
    for token in forbidden_tokens:
        if token and len(token) >= 3 and token in normalized:
            violations.append("contains_profile_token")
            break
    if password in set(history or []):
        violations.append("reused_password")
    longest_run = 1
    current_run = 1
    for left, right in zip(password, password[1:]):
        if left == right:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 1
    if longest_run >= 4:
        violations.append("repeated_character_run")
    elif longest_run == 1:
        score += 1
    if violations:
        strength = "reject"
    elif score >= 7:
        strength = "strong"
    elif score >= 5:
        strength = "acceptable"
    else:
        strength = "weak"
    return {"accepted": not violations, "strength": strength, "violations": violations}