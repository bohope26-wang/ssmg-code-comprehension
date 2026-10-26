def plan_restaurant_prep_schedule(menu_orders, ingredient_stock, stations, prep_rules):
    schedule = []
    shortages = []
    station_state = {}
    ingredient_state = {name: dict(info) for name, info in ingredient_stock.items()}
    prepared_tasks = []
    rejected_orders = []
    service_start = int(prep_rules.get("service_start_minute", 600))
    batch_window = int(prep_rules.get("batch_window_minutes", 20))
    default_prep = int(prep_rules.get("default_prep_minutes", 15))
    for station in stations:
        station_id = station.get("id")
        if not station_id:
            continue
        station_state[station_id] = {
            "skills": set(station.get("skills", [])),
            "capacity": int(station.get("capacity", 1) or 1),
            "available_at": int(station.get("available_at", service_start - 180)),
            "assigned": [],
            "cleaning_minutes": int(station.get("cleaning_minutes", 0) or 0),
        }
    for order in menu_orders:
        order_id = order.get("id")
        due_minute = int(order.get("due_minute", service_start) or service_start)
        party_size = int(order.get("party_size", 1) or 1)
        priority = int(order.get("priority", 5) or 5)
        if not order_id or party_size <= 0:
            rejected_orders.append({"id": order_id, "reason": "invalid_order"})
            continue
        for item in order.get("items", []):
            dish = item.get("dish")
            quantity = int(item.get("quantity", 1) or 1)
            recipe = prep_rules.get("recipes", {}).get(dish)
            if not dish or not recipe or quantity <= 0:
                rejected_orders.append({"id": order_id, "dish": dish, "reason": "invalid_dish"})
                continue
            missing = []
            reserved = []
            for ingredient, amount in recipe.get("ingredients", {}).items():
                needed = float(amount) * quantity
                available = float(ingredient_state.get(ingredient, {}).get("available", 0) or 0)
                if available < needed:
                    missing.append({"ingredient": ingredient, "needed": needed, "available": available})
                else:
                    reserved.append((ingredient, needed))
            if missing:
                shortages.append({"order_id": order_id, "dish": dish, "missing": missing})
                if prep_rules.get("drop_shortage_items", True):
                    continue
            for ingredient, needed in reserved:
                ingredient_state[ingredient]["available"] = float(ingredient_state[ingredient].get("available", 0) or 0) - needed
                ingredient_state[ingredient]["reserved"] = float(ingredient_state[ingredient].get("reserved", 0) or 0) + needed
            prep_minutes = int(recipe.get("prep_minutes", default_prep) or default_prep)
            cook_minutes = int(recipe.get("cook_minutes", 0) or 0)
            station_skill = recipe.get("station", "general")
            ready_by = due_minute - int(recipe.get("rest_minutes", 0) or 0)
            task = {
                "order_id": order_id,
                "dish": dish,
                "quantity": quantity,
                "party_size": party_size,
                "priority": priority,
                "station_skill": station_skill,
                "duration": prep_minutes + cook_minutes,
                "ready_by": ready_by,
                "allergens": set(recipe.get("allergens", [])),
                "hot": bool(recipe.get("hot", False)),
            }
            prepared_tasks.append(task)
    prepared_tasks.sort(key=lambda row: (row["ready_by"], row["priority"], -row["party_size"], row["dish"]))
    for task in prepared_tasks:
        candidates = []
        for station_id, state in station_state.items():
            if task["station_skill"] not in state["skills"] and "general" not in state["skills"]:
                continue
            allergen_penalty = 0
            previous_allergens = set()
            if state["assigned"]:
                previous_allergens = set(state["assigned"][-1].get("allergens", []))
            if previous_allergens and previous_allergens != task["allergens"]:
                allergen_penalty = state["cleaning_minutes"]
            earliest_start = state["available_at"] + allergen_penalty
            latest_start = task["ready_by"] - task["duration"]
            lateness = max(0, earliest_start - latest_start)
            candidates.append((lateness, earliest_start, station_id, allergen_penalty))
        if not candidates:
            rejected_orders.append({"id": task["order_id"], "dish": task["dish"], "reason": "no_station"})
            continue
        candidates.sort()
        lateness, start, station_id, cleaning = candidates[0]
        if cleaning:
            schedule.append(
                {
                    "type": "clean",
                    "station_id": station_id,
                    "start": start - cleaning,
                    "end": start,
                    "reason": "allergen_changeover",
                }
            )
        end = start + task["duration"]
        if end > task["ready_by"] + batch_window:
            rejected_orders.append({"id": task["order_id"], "dish": task["dish"], "reason": "too_late_to_prepare"})
            continue
        station_state[station_id]["available_at"] = end
        station_state[station_id]["assigned"].append(task)
        schedule.append(
            {
                "type": "prep",
                "station_id": station_id,
                "order_id": task["order_id"],
                "dish": task["dish"],
                "quantity": task["quantity"],
                "start": start,
                "end": end,
                "ready_by": task["ready_by"],
                "late_minutes": max(0, end - task["ready_by"]),
            }
        )
    schedule.sort(key=lambda row: (row["start"], row["station_id"], row.get("dish", "")))
    station_load = {}
    for station_id, state in station_state.items():
        busy = sum(item["duration"] for item in state["assigned"])
        station_load[station_id] = {"tasks": len(state["assigned"]), "busy_minutes": busy, "available_at": state["available_at"]}
    return {
        "schedule": schedule,
        "shortages": shortages,
        "rejected_orders": rejected_orders,
        "station_load": station_load,
        "remaining_ingredients": ingredient_state,
    }