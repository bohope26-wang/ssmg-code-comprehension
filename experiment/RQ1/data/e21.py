def build_warehouse_pick_waves(orders, inventory, zones, config):
    waves = []
    backorders = []
    inventory_state = {sku: dict(data) for sku, data in inventory.items()}
    zone_priority = {zone["id"]: int(zone.get("priority", 50) or 50) for zone in zones}
    cold_zones = {zone["id"] for zone in zones if zone.get("temperature") == "cold"}
    max_lines = int(config.get("max_lines_per_wave", 40))
    max_units = int(config.get("max_units_per_wave", 200))
    allow_cold_mix = bool(config.get("allow_cold_mix", False))
    def available_units(sku):
        record = inventory_state.get(sku, {})
        on_hand = int(record.get("on_hand", 0) or 0)
        reserved = int(record.get("reserved", 0) or 0)
        return max(0, on_hand - reserved)
    prepared_orders = []
    for order in orders:
        lines = []
        missing = []
        for line in order.get("lines", []):
            sku = line.get("sku")
            qty = int(line.get("quantity", 0) or 0)
            if not sku or qty <= 0:
                continue
            if available_units(sku) < qty:
                missing.append({"sku": sku, "requested": qty, "available": available_units(sku)})
            else:
                record = inventory_state.get(sku, {})
                lines.append(
                    {
                        "sku": sku,
                        "quantity": qty,
                        "zone": record.get("zone", "unknown"),
                        "fragile": bool(record.get("fragile")),
                    }
                )
        if missing:
            backorders.append({"order_id": order.get("id"), "missing": missing})
            if config.get("require_complete_order", True):
                continue
        if not lines:
            backorders.append({"order_id": order.get("id"), "missing": "no_pickable_lines"})
            continue
        priority = int(order.get("priority", 5) or 5)
        due = order.get("ship_by", "9999-12-31")
        cold = any(line["zone"] in cold_zones for line in lines)
        prepared_orders.append(
            {
                "id": order.get("id"),
                "priority": priority,
                "ship_by": due,
                "lines": lines,
                "cold": cold,
                "line_count": len(lines),
                "unit_count": sum(line["quantity"] for line in lines),
            }
        )
    prepared_orders.sort(
        key=lambda order: (
            order["priority"],
            order["ship_by"],
            min(zone_priority.get(line["zone"], 99) for line in order["lines"]),
            order["id"],
        )
    )
    current = None
    def start_wave(order):
        return {
            "orders": [],
            "lines": [],
            "zones": set(),
            "line_count": 0,
            "unit_count": 0,
            "cold": order["cold"],
            "fragile": False,
        }
    def close_wave(wave):
        if not wave or not wave["orders"]:
            return
        waves.append(
            {
                "orders": wave["orders"],
                "zones": sorted(wave["zones"], key=lambda z: zone_priority.get(z, 99)),
                "line_count": wave["line_count"],
                "unit_count": wave["unit_count"],
                "cold": wave["cold"],
                "fragile": wave["fragile"],
                "lines": wave["lines"],
            }
        )
    for order in prepared_orders:
        if current is None:
            current = start_wave(order)
        would_cross_lines = current["line_count"] + order["line_count"] > max_lines
        would_cross_units = current["unit_count"] + order["unit_count"] > max_units
        would_mix_cold = current["orders"] and current["cold"] != order["cold"] and not allow_cold_mix
        if would_cross_lines or would_cross_units or would_mix_cold:
            close_wave(current)
            current = start_wave(order)
        current["orders"].append(order["id"])
        current["line_count"] += order["line_count"]
        current["unit_count"] += order["unit_count"]
        current["cold"] = current["cold"] or order["cold"]
        for line in order["lines"]:
            sku = line["sku"]
            qty = line["quantity"]
            inventory_state[sku]["reserved"] = int(inventory_state[sku].get("reserved", 0) or 0) + qty
            current["zones"].add(line["zone"])
            current["fragile"] = current["fragile"] or line["fragile"]
            current["lines"].append({"order_id": order["id"], **line})
    close_wave(current)
    for index, wave in enumerate(waves, start=1):
        wave["wave_id"] = f"W{index:03d}"
        wave["estimated_minutes"] = 5 + wave["line_count"] * 2 + len(wave["zones"]) * 4
        if wave["fragile"]:
            wave["estimated_minutes"] += 6
        if wave["cold"]:
            wave["estimated_minutes"] += 8
    return {"waves": waves, "backorders": backorders, "inventory": inventory_state}