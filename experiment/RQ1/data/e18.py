def reconcile_bank_statement(ledger_entries, bank_rows, tolerances):
    matched = []
    unmatched_ledger = []
    unmatched_bank = []
    warnings = []
    amount_tolerance = float(tolerances.get("amount", 0.01))
    date_tolerance_days = int(tolerances.get("days", 2))
    def parse_date(value):
        if isinstance(value, datetime):
            return value.date()
        return datetime.fromisoformat(str(value)).date()
    ledger = []
    for index, entry in enumerate(ledger_entries):
        try:
            amount = round(float(entry.get("amount", 0)), 2)
            ledger.append(
                {
                    "index": index,
                    "id": entry.get("id", f"ledger-{index}"),
                    "date": parse_date(entry.get("date")),
                    "amount": amount,
                    "description": str(entry.get("description", "")).lower(),
                    "reference": str(entry.get("reference", "")).strip().lower(),
                    "account": entry.get("account"),
                    "matched": False,
                }
            )
        except (TypeError, ValueError):
            warnings.append({"source": "ledger", "index": index, "reason": "invalid_row"})
    bank = []
    for index, row in enumerate(bank_rows):
        try:
            amount = round(float(row.get("amount", 0)), 2)
            bank.append(
                {
                    "index": index,
                    "id": row.get("id", f"bank-{index}"),
                    "date": parse_date(row.get("date")),
                    "amount": amount,
                    "description": str(row.get("description", "")).lower(),
                    "reference": str(row.get("reference", "")).strip().lower(),
                    "matched": False,
                }
            )
        except (TypeError, ValueError):
            warnings.append({"source": "bank", "index": index, "reason": "invalid_row"})
    def score_pair(left, right):
        amount_delta = abs(left["amount"] - right["amount"])
        if amount_delta > amount_tolerance:
            return None
        date_delta = abs((left["date"] - right["date"]).days)
        if date_delta > date_tolerance_days:
            return None
        score = 100
        score -= amount_delta * 20
        score -= date_delta * 8
        if left["reference"] and left["reference"] == right["reference"]:
            score += 30
        elif left["reference"] and left["reference"] in right["description"]:
            score += 12
        if left["description"] and left["description"] in right["description"]:
            score += 10
        if left["amount"] == right["amount"]:
            score += 5
        return score
    candidates = []
    for left in ledger:
        for right in bank:
            score = score_pair(left, right)
            if score is not None:
                candidates.append((score, left["index"], right["index"]))
    candidates.sort(reverse=True)
    ledger_by_index = {row["index"]: row for row in ledger}
    bank_by_index = {row["index"]: row for row in bank}
    for score, ledger_index, bank_index in candidates:
        left = ledger_by_index[ledger_index]
        right = bank_by_index[bank_index]
        if left["matched"] or right["matched"]:
            continue
        left["matched"] = True
        right["matched"] = True
        matched.append(
            {
                "ledger_id": left["id"],
                "bank_id": right["id"],
                "score": round(score, 2),
                "amount_delta": round(left["amount"] - right["amount"], 2),
                "date_delta": (left["date"] - right["date"]).days,
            }
        )
    for left in ledger:
        if not left["matched"]:
            unmatched_ledger.append(
                {
                    "id": left["id"],
                    "amount": left["amount"],
                    "date": left["date"].isoformat(),
                    "reference": left["reference"],
                }
            )
    for right in bank:
        if not right["matched"]:
            unmatched_bank.append(
                {
                    "id": right["id"],
                    "amount": right["amount"],
                    "date": right["date"].isoformat(),
                    "reference": right["reference"],
                }
            )
    balance_delta = round(sum(row["amount"] for row in unmatched_ledger) - sum(row["amount"] for row in unmatched_bank), 2)
    status = "balanced" if not unmatched_ledger and not unmatched_bank else "exceptions"
    if abs(balance_delta) <= amount_tolerance and status == "exceptions":
        status = "timing_difference"
    return {
        "status": status,
        "matched": matched,
        "unmatched_ledger": unmatched_ledger,
        "unmatched_bank": unmatched_bank,
        "balance_delta": balance_delta,
        "warnings": warnings,
    }