from __future__ import annotations

import logging
from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any

from app.services.localization import tr
from app.services.metrics import disconnected_module_count, module_components, singleton_module_count
from app.services.schemas import (
    CFGPayload,
    RuntimeConfig,
    StageABOutput,
    StageCModule,
    StageCOutput,
    StageDCandidateReview,
    StageDModuleMetadata,
    StageDOutput,
    StageDQualityMetrics,
    StageDRepairRecord,
)


logger = logging.getLogger(__name__)


def verify_and_repair(
    cfg: CFGPayload,
    stage_ab: StageABOutput,
    stage_c: StageCOutput,
    runtime_config: RuntimeConfig,
) -> StageDOutput:
    logger.info("StageD start function=%s candidates=%s", runtime_config.function_name, len(stage_c.candidates))
    valid_bb_ids = {node.id for node in cfg.bb_nodes}
    candidate_states = [_candidate_to_state(candidate, valid_bb_ids, runtime_config.language) for candidate in stage_c.candidates]
    if not candidate_states:
        candidate_states = [_fallback_candidate_state(cfg, runtime_config.language)]

    reviews = [_review_candidate_state(state, cfg, valid_bb_ids, runtime_config.max_modules) for state in candidate_states]
    selected_state = _select_candidate_state(candidate_states, reviews)
    source_modules = deepcopy(selected_state["modules"])
    repairs: list[StageDRepairRecord] = []
    warnings: list[str] = []

    _drop_unknown_bbs(selected_state, valid_bb_ids, repairs, runtime_config.language)
    _resolve_duplicate_assignments(selected_state, cfg, repairs, runtime_config.language)
    _fill_missing_bbs(selected_state, valid_bb_ids, cfg, repairs, runtime_config.language)

    if runtime_config.enable_repair:
        _merge_tiny_modules(selected_state, cfg, repairs, runtime_config.language)
        _adjust_module_count(selected_state, runtime_config.max_modules, cfg, repairs, runtime_config.language)
        _repair_disconnected_modules(selected_state, cfg, repairs, warnings, runtime_config.language)
    else:
        warnings.append(tr(runtime_config.language, "warning.repair_disabled"))

    normalized_modules = _normalize_module_ids(selected_state["modules"])
    final_partition = _build_final_partition(normalized_modules)
    module_metadata = _build_module_metadata(normalized_modules, source_modules, stage_ab, runtime_config.language)
    quality_metrics = StageDQualityMetrics(
        coverage_ratio=round(len(final_partition) / max(1, len(valid_bb_ids)), 4),
        duplicate_assignment_count=_duplicate_count(normalized_modules),
        unknown_bb_count=sum(1 for bb in final_partition if bb not in valid_bb_ids),
        module_count=len(normalized_modules),
        singleton_module_count=singleton_module_count(final_partition),
        disconnected_module_count=disconnected_module_count(cfg, final_partition),
    )

    stage_d = StageDOutput(
        stage="stage_d_verification_and_repair_v1",
        function_name=runtime_config.function_name,
        selected_candidate_id=selected_state["candidate_id"],
        candidate_reviews=reviews,
        repairs=repairs,
        final_partition=final_partition,
        module_metadata=module_metadata,
        quality_metrics=quality_metrics,
        warnings=warnings,
    )
    logger.info("StageD done function=%s modules=%s repairs=%s", runtime_config.function_name, len(module_metadata), len(repairs))
    return stage_d


def _candidate_to_state(candidate: Any, valid_bb_ids: set[str], language: str) -> dict[str, Any]:
    modules: list[dict[str, Any]] = []
    for idx, module in enumerate(candidate.mods, start=1):
        if not isinstance(module, StageCModule):
            continue
        bb_ids = _unique_ordered([bb for bb in module.bbs if bb in valid_bb_ids])
        modules.append(
            {
                "id": module.id or f"T{idx}",
                "label": module.label or f"{tr(language, 'label.module')}{idx}",
                "desc": module.desc or tr(language, "fallback.module_desc", label=f"{tr(language, 'label.module')}{idx}".lower()),
                "more_specific_desc": module.more_specific_desc
                or tr(language, "fallback.module_specific", label=f"{tr(language, 'label.module')}{idx}".lower()),
                "bb_ids": bb_ids,
                "evi": [bb for bb in _unique_ordered(module.evi) if bb in bb_ids],
                "conf": int(module.conf),
            }
        )
    if not modules:
        modules = [
            {
                "id": "T1",
                "label": tr(language, "label.recovered"),
                "desc": tr(language, "fallback.recovered_module"),
                "more_specific_desc": tr(language, "fallback.recovered_specific"),
                "bb_ids": [],
                "evi": [],
                "conf": 45,
            }
        ]
    return {"candidate_id": candidate.id, "modules": modules}


def _fallback_candidate_state(cfg: CFGPayload, language: str) -> dict[str, Any]:
    bb_ids = sorted([node.id for node in cfg.bb_nodes], key=_bb_sort_key)
    return {
        "candidate_id": "C1",
        "modules": [
            {
                "id": "T1",
                "label": tr(language, "label.recovered"),
                "desc": tr(language, "fallback.recovered_from_deterministic"),
                "more_specific_desc": tr(language, "fallback.recovered_from_deterministic_specific"),
                "bb_ids": bb_ids,
                "evi": bb_ids[:2],
                "conf": 45,
            }
        ],
    }


def _review_candidate_state(state: dict[str, Any], cfg: CFGPayload, valid_bb_ids: set[str], max_modules: int) -> StageDCandidateReview:
    violations: list[dict[str, Any]] = []
    warns: list[dict[str, Any]] = []
    assignment: dict[str, list[str]] = defaultdict(list)
    unknown_count = 0

    for module in state["modules"]:
        if not module["bb_ids"]:
            violations.append({"type": "non_empty_module_check", "module_id": module["id"]})
        for bb_id in module["bb_ids"]:
            if bb_id not in valid_bb_ids:
                unknown_count += 1
                violations.append({"type": "unknown_bb_check", "bb_id": bb_id, "module_id": module["id"]})
            assignment[bb_id].append(module["id"])

    for bb_id, owners in assignment.items():
        if len(owners) > 1:
            violations.append({"type": "uniqueness_check", "bb_id": bb_id, "modules": owners})

    missing = sorted(valid_bb_ids - set(assignment.keys()), key=_bb_sort_key)
    for bb_id in missing:
        violations.append({"type": "coverage_check", "bb_id": bb_id})

    if len(state["modules"]) > max_modules or len(state["modules"]) < 1:
        warns.append({"type": "module_count_check", "module_count": len(state["modules"]), "max_modules": max_modules})

    for module in state["modules"]:
        size = len(module["bb_ids"])
        if 0 < size <= 1:
            warns.append({"type": "small_module_check", "module_id": module["id"], "size": size})
        if len(module_components(cfg, module["bb_ids"])) > 1:
            warns.append({"type": "connectivity_check", "module_id": module["id"]})

    boundary_warns = _boundary_sanity_warnings(cfg, assignment)
    warns.extend(boundary_warns)

    avg_conf = 0.0
    if state["modules"]:
        avg_conf = sum(module.get("conf", 50) for module in state["modules"]) / (100 * len(state["modules"]))
    quality = max(0.0, min(1.0, round(0.55 + avg_conf * 0.35 - 0.18 * len(violations) - 0.03 * len(warns), 3)))
    return StageDCandidateReview(
        candidate_id=state["candidate_id"],
        hard_valid=len(violations) == 0,
        quality_score=quality,
        violations=violations,
        warnings=warns,
    )


def _boundary_sanity_warnings(cfg: CFGPayload, assignment: dict[str, list[str]]) -> list[dict[str, Any]]:
    warns: list[dict[str, Any]] = []
    main_edges = [edge for edge in cfg.cfg_edges if edge.type in {"main", "loop", "continue"}]
    transitions = 0
    for edge in main_edges:
        from_mod = assignment.get(edge.from_, [None])[0]
        to_mod = assignment.get(edge.to, [None])[0]
        if not from_mod or not to_mod:
            continue
        if from_mod != to_mod:
            transitions += 1
    if main_edges and transitions > max(1, len(main_edges) // 2):
        warns.append({"type": "boundary_sanity_check", "transitions": transitions, "main_edges": len(main_edges)})
    return warns


def _select_candidate_state(states: list[dict[str, Any]], reviews: list[StageDCandidateReview]) -> dict[str, Any]:
    review_by_id = {review.candidate_id: review for review in reviews}
    valid = [state for state in states if review_by_id[state["candidate_id"]].hard_valid]
    ranked = valid if valid else states
    ranked.sort(key=lambda item: review_by_id[item["candidate_id"]].quality_score, reverse=True)
    return deepcopy(ranked[0])


def _drop_unknown_bbs(state: dict[str, Any], valid_bb_ids: set[str], repairs: list[StageDRepairRecord], language: str) -> None:
    for module in state["modules"]:
        keep = [bb for bb in module["bb_ids"] if bb in valid_bb_ids]
        removed = [bb for bb in module["bb_ids"] if bb not in valid_bb_ids]
        if removed:
            repairs.append(
                StageDRepairRecord(
                    type="drop_unknown_bb",
                    from_module=module["id"],
                    reason=tr(language, "repair.drop_unknown"),
                    details={"removed": removed},
                )
            )
        module["bb_ids"] = keep
        module["evi"] = [bb for bb in module.get("evi", []) if bb in keep]


def _resolve_duplicate_assignments(state: dict[str, Any], cfg: CFGPayload, repairs: list[StageDRepairRecord], language: str) -> None:
    assignment = _assignment_map(state["modules"])
    module_lookup = {module["id"]: module for module in state["modules"]}
    for bb_id, owners in assignment.items():
        if len(owners) <= 1:
            continue
        chosen = _pick_best_owner_for_bb(bb_id, owners, module_lookup, cfg)
        for owner in owners:
            if owner == chosen:
                continue
            module_lookup[owner]["bb_ids"] = [bb for bb in module_lookup[owner]["bb_ids"] if bb != bb_id]
        repairs.append(
            StageDRepairRecord(
                type="resolve_duplicate_assignment",
                from_module=",".join(owners),
                to_module=chosen,
                bb_id=bb_id,
                reason=tr(language, "repair.resolve_duplicate"),
            )
        )


def _fill_missing_bbs(state: dict[str, Any], valid_bb_ids: set[str], cfg: CFGPayload, repairs: list[StageDRepairRecord], language: str) -> None:
    module_lookup = {module["id"]: module for module in state["modules"]}
    assigned = {bb for module in state["modules"] for bb in module["bb_ids"]}
    missing = sorted(valid_bb_ids - assigned, key=_bb_sort_key)
    for bb_id in missing:
        target = _pick_best_owner_for_bb(bb_id, list(module_lookup.keys()), module_lookup, cfg)
        if not target:
            target = "T_RECOVERED"
            if target not in module_lookup:
                module_lookup[target] = {
                    "id": target,
                    "label": tr(language, "label.recovered"),
                    "desc": tr(language, "fallback.repair_created_desc"),
                    "more_specific_desc": tr(language, "fallback.repair_created_specific"),
                    "bb_ids": [],
                    "evi": [],
                    "conf": 40,
                }
                state["modules"].append(module_lookup[target])
        module_lookup[target]["bb_ids"].append(bb_id)
        repairs.append(StageDRepairRecord(type="assign_missing_bb", to_module=target, bb_id=bb_id, reason=tr(language, "repair.assign_missing")))


def _merge_tiny_modules(state: dict[str, Any], cfg: CFGPayload, repairs: list[StageDRepairRecord], language: str) -> None:
    while True:
        tiny = None
        for module in state["modules"]:
            if 0 < len(module["bb_ids"]) <= 1 and len(state["modules"]) > 1:
                tiny = module
                break
        if not tiny:
            return
        target = _pick_best_merge_target(tiny["id"], state["modules"], cfg)
        if not target:
            return
        target_module = _find_module(state["modules"], target)
        if not target_module:
            return
        target_module["bb_ids"] = _unique_ordered(target_module["bb_ids"] + tiny["bb_ids"])
        target_module["evi"] = _unique_ordered(target_module.get("evi", []) + tiny.get("evi", []))
        state["modules"] = [module for module in state["modules"] if module["id"] != tiny["id"]]
        repairs.append(
            StageDRepairRecord(
                type="merge_small_module",
                from_module=tiny["id"],
                to_module=target,
                reason=tr(language, "repair.merge_small"),
            )
        )


def _adjust_module_count(state: dict[str, Any], max_modules: int, cfg: CFGPayload, repairs: list[StageDRepairRecord], language: str) -> None:
    while len(state["modules"]) > max_modules:
        state["modules"].sort(key=lambda item: (len(item["bb_ids"]), item.get("conf", 50)))
        source = state["modules"][0]
        target = _pick_best_merge_target(source["id"], state["modules"], cfg)
        if not target:
            break
        target_module = _find_module(state["modules"], target)
        if not target_module:
            break
        target_module["bb_ids"] = _unique_ordered(target_module["bb_ids"] + source["bb_ids"])
        target_module["evi"] = _unique_ordered(target_module.get("evi", []) + source.get("evi", []))
        state["modules"] = [module for module in state["modules"] if module["id"] != source["id"]]
        repairs.append(
            StageDRepairRecord(
                type="reduce_module_count",
                from_module=source["id"],
                to_module=target,
                reason=tr(language, "repair.reduce_count"),
            )
        )


def _repair_disconnected_modules(
    state: dict[str, Any],
    cfg: CFGPayload,
    repairs: list[StageDRepairRecord],
    warnings: list[str],
    language: str,
) -> None:
    module_lookup = {module["id"]: module for module in state["modules"]}
    for module in list(state["modules"]):
        components = module_components(cfg, module["bb_ids"])
        if len(components) <= 1:
            continue
        components.sort(key=len, reverse=True)
        keep = components[0]
        for comp in components[1:]:
            for bb_id in comp:
                target = _pick_best_owner_for_bb(bb_id, [mid for mid in module_lookup if mid != module["id"]], module_lookup, cfg)
                if not target:
                    warnings.append(tr(language, "warning.disconnected_not_relocated", bb_id=bb_id, module_id=module["id"]))
                    continue
                _move_bb(state["modules"], bb_id, module["id"], target)
                repairs.append(
                    StageDRepairRecord(
                        type="repair_disconnected_module",
                        from_module=module["id"],
                        to_module=target,
                        bb_id=bb_id,
                        reason=tr(language, "repair.disconnected"),
                    )
                )
        module["bb_ids"] = [bb for bb in module["bb_ids"] if bb in keep]


def _normalize_module_ids(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    for module in modules:
        bb_ids = _unique_ordered(module.get("bb_ids", []))
        if bb_ids:
            cleaned.append({**module, "bb_ids": bb_ids})
    cleaned.sort(key=lambda item: _bb_sort_key(item["bb_ids"][0]))
    result: list[dict[str, Any]] = []
    for idx, module in enumerate(cleaned, start=1):
        result.append({**module, "module_id": f"M{idx}"})
    return result


def _build_final_partition(modules: list[dict[str, Any]]) -> dict[str, str]:
    partition: dict[str, str] = {}
    for module in modules:
        for bb_id in module["bb_ids"]:
            partition[bb_id] = module["module_id"]
    return partition


def _build_module_metadata(
    modules: list[dict[str, Any]],
    source_modules: list[dict[str, Any]],
    stage_ab: StageABOutput,
    language: str,
) -> list[StageDModuleMetadata]:
    source_lookup = {module["id"]: set(module.get("bb_ids", [])) for module in source_modules}
    ab_lookup = {item.id: item for item in stage_ab.bb}
    metadata: list[StageDModuleMetadata] = []
    for module in modules:
        bb_set = set(module["bb_ids"])
        best_source_id = ""
        best_ratio = 0.0
        for source_id, source_bbs in source_lookup.items():
            if not source_bbs:
                continue
            overlap = len(bb_set & source_bbs) / max(1, len(bb_set))
            if overlap > best_ratio:
                best_ratio = overlap
                best_source_id = source_id
        source_module = _find_source_module(source_modules, best_source_id)
        desc_status = _desc_status(best_ratio)
        source_label = source_module.get("label", "") if source_module else ""
        source_desc = source_module.get("desc", "") if source_module else ""
        source_more_specific_desc = source_module.get("more_specific_desc", "") if source_module else ""
        label = source_label or _derive_label_from_ab(module["bb_ids"], ab_lookup, language)
        desc = source_desc if desc_status != "invalidated" else _derive_desc_from_ab(module["bb_ids"], ab_lookup, label, language)
        more_specific_desc = (
            source_more_specific_desc
            if source_more_specific_desc and desc_status != "invalidated"
            else _derive_more_specific_desc_from_ab(module["bb_ids"], ab_lookup, label, language)
        )
        evi = _evidence_from_source_or_module(source_module, module["bb_ids"])
        confidence = _derive_confidence(source_module, best_ratio)
        risk = _derive_risk(module["bb_ids"], ab_lookup, desc_status)
        metadata.append(
            StageDModuleMetadata(
                module_id=module["module_id"],
                source_temp_module_id=best_source_id or "N/A",
                label=label,
                desc=desc,
                more_specific_desc=more_specific_desc,
                desc_status=desc_status,
                overlap_ratio=round(best_ratio, 3),
                bb_ids=module["bb_ids"],
                evidence_bb_ids=evi,
                confidence=confidence,
                risk=risk,
            )
        )
    return metadata


def _find_source_module(source_modules: list[dict[str, Any]], module_id: str) -> dict[str, Any] | None:
    for module in source_modules:
        if module["id"] == module_id:
            return module
    return None


def _desc_status(overlap_ratio: float) -> str:
    if overlap_ratio >= 0.7:
        return "inherited"
    if overlap_ratio >= 0.4:
        return "weakly_inherited"
    return "invalidated"


def _derive_label_from_ab(bb_ids: list[str], ab_lookup: dict[str, Any], language: str) -> str:
    counts: Counter[str] = Counter()
    for bb_id in bb_ids:
        item = ab_lookup.get(bb_id)
        if not item or not item.rc:
            continue
        top = sorted(item.rc, key=lambda row: _safe_int(row[1] if len(row) > 1 else 0), reverse=True)[0]
        if top:
            counts[str(top[0]).strip() or tr(language, "label.module")] += 1
    if not counts:
        return tr(language, "label.module")
    role = counts.most_common(1)[0][0]
    return role[0].upper() + role[1:] if role else tr(language, "label.module")


def _derive_desc_from_ab(bb_ids: list[str], ab_lookup: dict[str, Any], label: str, language: str) -> str:
    uncertain = 0
    for bb_id in bb_ids:
        item = ab_lookup.get(bb_id)
        if not item:
            continue
        if item.u == "H":
            uncertain += 1
    base = tr(language, "fallback.invalidated_claim", label=label.lower()).rstrip(".。")
    suffix = tr(language, "fallback.uncertain_boundary_suffix") if uncertain > 0 else ("." if language == "en" else "。")
    return f"{base}{suffix}"


def _derive_more_specific_desc_from_ab(bb_ids: list[str], ab_lookup: dict[str, Any], label: str, language: str) -> str:
    if not bb_ids:
        return tr(language, "fallback.more_specific_empty", label=label.lower())

    control_roles: list[str] = []
    uncertain = 0
    for bb_id in bb_ids:
        item = ab_lookup.get(bb_id)
        if not item:
            continue
        role = str(item.cr or "").strip()
        if role and role not in control_roles:
            control_roles.append(role)
        if item.u == "H":
            uncertain += 1

    flow_hint = ", ".join(control_roles[:3]) if control_roles else ("local control flow" if language == "en" else "局部控制流")
    uncertainty_hint = (
        tr(language, "fallback.uncertainty_hint")
        if uncertain > 0
        else ""
    )
    return tr(language, "fallback.more_specific", label=label.lower(), flow_hint=flow_hint, uncertainty_hint=uncertainty_hint)


def _evidence_from_source_or_module(source_module: dict[str, Any] | None, bb_ids: list[str]) -> list[str]:
    bb_set = set(bb_ids)
    if source_module:
        evi = [bb for bb in source_module.get("evi", []) if bb in bb_set]
        if evi:
            return evi[: min(3, len(evi))]
    return bb_ids[: min(3, len(bb_ids))]


def _derive_confidence(source_module: dict[str, Any] | None, overlap_ratio: float) -> int:
    source_conf = int(source_module.get("conf", 55)) if source_module else 55
    blended = int(round(source_conf * overlap_ratio + 50 * (1 - overlap_ratio)))
    return max(0, min(100, blended))


def _derive_risk(bb_ids: list[str], ab_lookup: dict[str, Any], desc_status: str) -> str:
    if not bb_ids:
        return "H"
    high = 0
    medium = 0
    for bb_id in bb_ids:
        item = ab_lookup.get(bb_id)
        if not item:
            medium += 1
            continue
        if item.u == "H":
            high += 1
        elif item.u == "M":
            medium += 1
    ratio_h = high / len(bb_ids)
    ratio_m = medium / len(bb_ids)
    if desc_status == "invalidated" and ratio_h >= 0.2:
        return "H"
    if ratio_h >= 0.45:
        return "H"
    if ratio_h + ratio_m >= 0.45:
        return "M"
    return "L"


def _pick_best_owner_for_bb(
    bb_id: str,
    candidate_modules: list[str],
    module_lookup: dict[str, dict[str, Any]],
    cfg: CFGPayload,
) -> str | None:
    if not candidate_modules:
        return None
    neighbors = _neighbors_of_bb(bb_id, cfg)
    best_module = None
    best_score = -10**9
    for module_id in candidate_modules:
        module = module_lookup.get(module_id)
        if not module:
            continue
        members = set(module.get("bb_ids", []))
        if not members:
            score = 0.0
        else:
            neighbor_hits = sum(1 for nb in neighbors if nb in members)
            score = neighbor_hits * 3.0 - len(members) * 0.01
        if score > best_score:
            best_score = score
            best_module = module_id
    return best_module


def _pick_best_merge_target(source_module_id: str, modules: list[dict[str, Any]], cfg: CFGPayload) -> str | None:
    source = _find_module(modules, source_module_id)
    if not source:
        return None
    source_set = set(source["bb_ids"])
    best = None
    best_score = -10**9
    for module in modules:
        if module["id"] == source_module_id:
            continue
        target_set = set(module.get("bb_ids", []))
        score = 0
        for edge in cfg.cfg_edges:
            cross = (edge.from_ in source_set and edge.to in target_set) or (edge.to in source_set and edge.from_ in target_set)
            if cross:
                score += 1
        if score > best_score:
            best_score = score
            best = module["id"]
    if best:
        return best
    for module in modules:
        if module["id"] != source_module_id:
            return module["id"]
    return None


def _move_bb(modules: list[dict[str, Any]], bb_id: str, from_module: str, to_module: str) -> None:
    source = _find_module(modules, from_module)
    target = _find_module(modules, to_module)
    if not source or not target:
        return
    source["bb_ids"] = [bb for bb in source["bb_ids"] if bb != bb_id]
    if bb_id not in target["bb_ids"]:
        target["bb_ids"].append(bb_id)


def _find_module(modules: list[dict[str, Any]], module_id: str) -> dict[str, Any] | None:
    for module in modules:
        if module["id"] == module_id:
            return module
    return None


def _assignment_map(modules: list[dict[str, Any]]) -> dict[str, list[str]]:
    assignment: dict[str, list[str]] = defaultdict(list)
    for module in modules:
        for bb_id in module.get("bb_ids", []):
            assignment[bb_id].append(module["id"])
    return assignment


def _neighbors_of_bb(bb_id: str, cfg: CFGPayload) -> set[str]:
    neighbors: set[str] = set()
    for edge in cfg.cfg_edges:
        if edge.from_ == bb_id:
            neighbors.add(edge.to)
        if edge.to == bb_id:
            neighbors.add(edge.from_)
    return neighbors


def _duplicate_count(modules: list[dict[str, Any]]) -> int:
    counter: Counter[str] = Counter()
    for module in modules:
        for bb_id in module["bb_ids"]:
            counter[bb_id] += 1
    return sum(1 for value in counter.values() if value > 1)


def _unique_ordered(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _bb_sort_key(bb_id: str) -> int:
    if bb_id.startswith("BB") and bb_id[2:].isdigit():
        return int(bb_id[2:])
    return 10**9
