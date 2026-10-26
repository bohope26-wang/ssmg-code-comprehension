def plan_delivery_batches(orders, vehicle_capacity, priority_zones):
    if vehicle_capacity <= 0:
        raise ValueError("vehicle_capacity must be positive")

    prepared = []
    skipped = []
    priority_zones = set(priority_zones or [])

    for order in orders:
        weight = float(order.get("weight", 0) or 0)
        if weight <= 0:
            skipped.append({"id": order.get("id"), "reason": "invalid_weight"})
            continue
        if weight > vehicle_capacity:
            skipped.append({"id": order.get("id"), "reason": "too_heavy"})
            continue
        prepared.append(
            {
                "id": order.get("id"),
                "zone": order.get("zone", "unknown"),
                "weight": weight,
                "deadline": order.get("deadline", "9999-12-31"),
                "priority": order.get("zone") in priority_zones,
            }
        )

    prepared.sort(key=lambda row: (not row["priority"], row["deadline"], row["zone"]))

    batches = []
    current = {"orders": [], "zones": set(), "weight": 0.0, "priority": False}

    for order in prepared:
        would_cross_capacity = current["weight"] + order["weight"] > vehicle_capacity
        would_mix_priority = current["orders"] and current["priority"] != order["priority"]
        would_cross_zone_limit = order["zone"] not in current["zones"] and len(current["zones"]) >= 2

        if would_cross_capacity or would_mix_priority or would_cross_zone_limit:
            batches.append(
                {
                    "orders": current["orders"],
                    "zones": sorted(current["zones"]),
                    "weight": round(current["weight"], 2),
                    "priority": current["priority"],
                }
            )
            current = {"orders": [], "zones": set(), "weight": 0.0, "priority": order["priority"]}

        current["orders"].append(order["id"])
        current["zones"].add(order["zone"])
        current["weight"] += order["weight"]
        current["priority"] = current["priority"] or order["priority"]

    if current["orders"]:
        batches.append(
            {
                "orders": current["orders"],
                "zones": sorted(current["zones"]),
                "weight": round(current["weight"], 2),
                "priority": current["priority"],
            }
        )

    return {"batches": batches, "skipped": skipped}