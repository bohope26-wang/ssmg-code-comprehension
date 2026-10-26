def part(
    cfg: Dict[str, Any],
    k_max: int,
    *,
    source_code: Optional[str] = None,
    blueprint_cache: Optional[str] = None,
    min_module_size: int = 2,
    weights_json: Optional[str] = None,
    debug_out: Optional[str] = None,
) -> Dict[str, str]: 
    bb_by_id = {bb["id"]: bb for bb in cfg.get("bb_nodes", []) or []}
    node_ids = [bb["id"] for bb in cfg.get("bb_nodes", []) or []]
    if not node_ids:
        return {}
    blueprint = get_blueprint(source_code, cache_path=blueprint_cache)
    call_hints: Dict[str, List[str]] = blueprint.get("call_hints", {})
    if STAGE_UNKNOWN not in call_hints:
        call_hints[STAGE_UNKNOWN] = []
    stages_in_order = [s for s in (blueprint.get("stages") or []) if isinstance(s, str) and s.strip()]
    if STAGE_UNKNOWN not in stages_in_order:
        stages_in_order.append(STAGE_UNKNOWN)
    stage_order: Dict[str, int] = {st: i for i, st in enumerate(stages_in_order)}
    stage_order.setdefault(STAGE_UNKNOWN, 10**9)
    kw_stage_cnt = _keyword_stage_counts(call_hints)
    stage_guess_by_id: Dict[str, StageGuess] = {
        bid: guess_stage(bb_by_id.get(bid, {}), call_hints, stage_order, kw_stage_cnt)
        for bid in node_ids
    }
    stage_by_id = _propagate_stages(cfg, stage_guess_by_id, stage_order, max_passes=3)
    print("[Stage counts: evidence]", Counter(sg.stage for sg in stage_guess_by_id.values()))
    print("[Stage counts: after propagation]", Counter(stage_by_id.values()))
    fctx = compute_function_context(cfg, stage_by_id, stages_in_order)
    pair_rows = build_pair_rows(cfg, bb_by_id, stage_by_id, fctx)
    scorer = load_scorer(weights_json)
    row_by_pair: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in pair_rows:
        score, p_cut = scorer.score(row)
        row["score"] = float(score)
        row["p_cut"] = float(p_cut)
        row["sim"] = float(1.0 - p_cut)
        row_by_pair[_pair_key(row["u"], row["v"])] = row
    edges_uv: List[Tuple[float, str, str, float]] = []
    for row in pair_rows:
        edges_uv.append((row["sim"], row["u"], row["v"], row["score"]))
    edges_uv.sort(key=lambda x: (x[0], x[3]), reverse=True)
    dsu = _DSU(node_ids)
    forest_edges: List[Tuple[float, str, str, float]] = []
    for sim, a, b, score in edges_uv:
        if dsu.union(a, b):
            forest_edges.append((sim, a, b, score))
    kept = {(a, b) for _, a, b, _ in forest_edges}
    comps = connected_components(node_ids, list(kept))
    if not forest_edges and len(node_ids) > 1:
        comps = [[n] for n in node_ids]
    forest_rows: List[Dict[str, Any]] = []
    for sim, a, b, score in forest_edges:
        row = row_by_pair.get(_pair_key(a, b), {"pair_id": f"{a}|{b}", "u": a, "v": b, "score": score, "p_cut": 1.0 - sim, "sim": sim})
        forest_rows.append(row)
        row["is_forest_edge"] = True
    for row in pair_rows:
        row.setdefault("is_forest_edge", False)
        row.setdefault("cut_applied", False)
        row.setdefault("cut_rank", None)
        row.setdefault("cut_rejected_reason", "")
    forest_rows.sort(key=lambda r: (float(r["score"]), float(r["p_cut"])), reverse=True)
    keep_edges = [(_pair_key(a, b)[0], _pair_key(a, b)[1]) for _, a, b, _ in forest_edges]
    current_comps = connected_components(node_ids, keep_edges)
    rank = 0
    for row in forest_rows:
        if len(current_comps) >= k_max:
            break
        rank += 1
        row["cut_rank"] = rank
        cand = _pair_key(row["u"], row["v"])
        tentative_keep = [e for e in keep_edges if e != cand]
        tentative_comps = connected_components(node_ids, tentative_keep)
        if violates_min_size(tentative_comps, min_module_size):
            row["cut_applied"] = False
            row["cut_rejected_reason"] = "min_size_violation"
            continue
        keep_edges = tentative_keep
        current_comps = tentative_comps
        row["cut_applied"] = True
    comps = current_comps
    def comp_key(comp: List[str]) -> Tuple[int, int, str]:
        has_entry = 0 if "ENTRY" in comp else 1
        min_line = 10**9
        for bid in comp:
            bb = bb_by_id.get(bid, {})
            span = bb.get("span") or [10**9, 10**9]
            if isinstance(span, list) and span:
                min_line = min(min_line, int(span[0]))
        return (has_entry, min_line, "|".join(sorted(comp)))
    comps.sort(key=comp_key)
    partition: Dict[str, str] = {}
    for idx, members in enumerate(comps, start=1):
        mid = f"M{idx}"
        for bb_id in members:
            partition[bb_id] = mid
    missing = [x for x in node_ids if x not in partition]
    if missing:
        print("[PARTITION BUG] missing ids:", missing)
    if debug_out:
        debug_payload = {
            "function": cfg.get("function", {}),
            "blueprint": blueprint,
            "function_context": fctx,
            "stage_guess": {
                bid: {
                    "stage": sg.stage,
                    "candidates": sg.candidates,
                    "is_evidence": sg.is_evidence,
                }
                for bid, sg in stage_guess_by_id.items()
            },
            "stage_final": stage_by_id,
            "pair_rows": pair_rows,
            "forest_edges": [
                {"u": a, "v": b, "sim": sim, "score": score}
                for sim, a, b, score in forest_edges
            ],
            "final_components": comps,
            "partition": partition,
            "config": {
                "k_max": k_max,
                "min_module_size": min_module_size,
                "weights_json": weights_json,
                "feature_order": FEATURE_ORDER,
                "feature_version": "no_pred_v1",
            },
        }
        dump_json(debug_payload, debug_out)
    return partition
