def simulate_elevator_dispatch(requests, cars, building):
    min_floor = int(building.get("min_floor", 0))
    max_floor = int(building.get("max_floor", 20))
    capacity = int(building.get("capacity", 8))
    tick_seconds = int(building.get("tick_seconds", 5))
    car_state = {}
    timeline = []
    pending = deque()
    completed = []
    rejected = []
    for car in cars:
        car_id = car.get("id")
        if not car_id:
            continue
        car_state[car_id] = {
            "floor": int(car.get("floor", min_floor)),
            "direction": car.get("direction", "idle"),
            "passengers": [],
            "targets": set(car.get("targets", [])),
            "load": int(car.get("load", 0) or 0),
            "out_of_service": bool(car.get("out_of_service")),
        }
    for index, request in enumerate(requests):
        origin = int(request.get("origin", min_floor))
        destination = int(request.get("destination", min_floor))
        if origin < min_floor or origin > max_floor or destination < min_floor or destination > max_floor:
            rejected.append({"index": index, "reason": "floor_out_of_range"})
            continue
        if origin == destination:
            rejected.append({"index": index, "reason": "same_origin_destination"})
            continue
        pending.append(
            {
                "id": request.get("id", f"request-{index}"),
                "origin": origin,
                "destination": destination,
                "time": int(request.get("time", 0) or 0),
                "direction": "up" if destination > origin else "down",
                "assigned": None,
                "picked_at": None,
            }
        )
    pending = deque(sorted(pending, key=lambda row: row["time"]))
    active_requests = []
    current_time = 0
    max_ticks = int(building.get("max_ticks", 500))
    def distance_score(state, request):
        if state["out_of_service"]:
            return None
        if state["load"] >= capacity:
            return None
        distance = abs(state["floor"] - request["origin"])
        direction_penalty = 0
        if state["direction"] != "idle" and state["direction"] != request["direction"]:
            direction_penalty = 5
        target_penalty = len(state["targets"])
        return distance * 2 + direction_penalty + target_penalty
    def choose_car(request):
        best = None
        for car_id, state in car_state.items():
            score = distance_score(state, request)
            if score is None:
                continue
            candidate = (score, abs(state["floor"] - request["origin"]), car_id)
            if best is None or candidate < best:
                best = candidate
        return best[2] if best else None
    for _ in range(max_ticks):
        while pending and pending[0]["time"] <= current_time:
            request = pending.popleft()
            car_id = choose_car(request)
            if car_id is None:
                active_requests.append(request)
            else:
                request["assigned"] = car_id
                car_state[car_id]["targets"].add(request["origin"])
                active_requests.append(request)
        for request in active_requests:
            if request["assigned"] is None:
                car_id = choose_car(request)
                if car_id is not None:
                    request["assigned"] = car_id
                    car_state[car_id]["targets"].add(request["origin"])
        for car_id, state in car_state.items():
            if state["out_of_service"]:
                continue
            if not state["targets"]:
                state["direction"] = "idle"
                continue
            next_target = min(state["targets"], key=lambda floor: abs(floor - state["floor"]))
            if next_target > state["floor"]:
                state["floor"] += 1
                state["direction"] = "up"
            elif next_target < state["floor"]:
                state["floor"] -= 1
                state["direction"] = "down"
            else:
                state["targets"].remove(next_target)
            boarded = []
            for request in active_requests:
                if request["assigned"] != car_id or request["picked_at"] is not None:
                    continue
                if request["origin"] == state["floor"] and state["load"] < capacity:
                    request["picked_at"] = current_time
                    state["passengers"].append(request)
                    state["targets"].add(request["destination"])
                    state["load"] += 1
                    boarded.append(request["id"])
            dropped = []
            remaining_passengers = []
            for passenger in state["passengers"]:
                if passenger["destination"] == state["floor"]:
                    passenger["completed_at"] = current_time
                    completed.append(passenger)
                    state["load"] -= 1
                    dropped.append(passenger["id"])
                else:
                    remaining_passengers.append(passenger)
            state["passengers"] = remaining_passengers
            if boarded or dropped:
                timeline.append(
                    {
                        "time": current_time,
                        "car_id": car_id,
                        "floor": state["floor"],
                        "boarded": boarded,
                        "dropped": dropped,
                    }
                )
        active_requests = [request for request in active_requests if "completed_at" not in request]
        if not pending and not active_requests and all(not state["passengers"] for state in car_state.values()):
            break
        current_time += tick_seconds
    abandoned = [
        {"id": request["id"], "origin": request["origin"], "destination": request["destination"]}
        for request in active_requests
        if "completed_at" not in request
    ]
    metrics = {
        "completed": len(completed),
        "rejected": len(rejected),
        "abandoned": len(abandoned),
        "average_wait": round(
            sum((request.get("picked_at", current_time) - request["time"]) for request in completed) / max(1, len(completed)),
            2,
        ),
    }
    return {"timeline": timeline, "completed": completed, "rejected": rejected, "abandoned": abandoned, "metrics": metrics}