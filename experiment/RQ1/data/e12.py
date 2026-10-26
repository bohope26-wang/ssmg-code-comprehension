def build_invoice_summary(items, customer, tax_table, coupons):
    subtotal = 0.0
    taxable_total = 0.0
    discount_total = 0.0
    line_summaries = []
    warnings = []

    if not items:
        return {
            "subtotal": 0.0,
            "discount": 0.0,
            "tax": 0.0,
            "total": 0.0,
            "lines": [],
            "warnings": ["empty_invoice"],
        }

    for index, item in enumerate(items, start=1):
        sku = str(item.get("sku", "")).strip()
        quantity = int(item.get("quantity", 0) or 0)
        unit_price = float(item.get("unit_price", 0) or 0)
        category = item.get("category", "general")
        taxable = bool(item.get("taxable", True))

        if not sku:
            warnings.append(f"line_{index}_missing_sku")
        if quantity <= 0:
            warnings.append(f"line_{index}_non_positive_quantity")
            continue
        if unit_price < 0:
            warnings.append(f"line_{index}_negative_price")
            unit_price = 0.0

        line_total = quantity * unit_price
        line_discount = 0.0

        for coupon in coupons or []:
            applies_to = coupon.get("category")
            min_qty = int(coupon.get("min_quantity", 1) or 1)
            if applies_to not in (None, category):
                continue
            if quantity < min_qty:
                continue
            if coupon.get("type") == "percent":
                line_discount += line_total * float(coupon.get("value", 0)) / 100
            elif coupon.get("type") == "fixed":
                line_discount += float(coupon.get("value", 0))

        if customer.get("tier") == "gold" and category != "service":
            line_discount += line_total * 0.03
        if customer.get("tax_exempt"):
            taxable = False

        line_discount = min(line_discount, line_total)
        net_line = line_total - line_discount
        subtotal += line_total
        discount_total += line_discount
        if taxable:
            taxable_total += net_line

        line_summaries.append(
            {
                "sku": sku,
                "quantity": quantity,
                "gross": round(line_total, 2),
                "discount": round(line_discount, 2),
                "net": round(net_line, 2),
                "taxable": taxable,
            }
        )

    state = customer.get("state", "default")
    tax_rate = float(tax_table.get(state, tax_table.get("default", 0)) or 0)
    tax = taxable_total * tax_rate
    total = subtotal - discount_total + tax

    if total < 0:
        warnings.append("negative_total_corrected")
        total = 0.0

    return {
        "subtotal": round(subtotal, 2),
        "discount": round(discount_total, 2),
        "tax": round(tax, 2),
        "total": round(total, 2),
        "lines": line_summaries,
        "warnings": warnings,
    }