from __future__ import annotations

from typing import Any

from app.services.localization import tr
from app.services.schemas import CFGPayload, ModuleEvidenceOutput, StageABOutput, StageCOutput, StageDOutput


def compile_module_evidence(
    *,
    cfg: CFGPayload,
    stage_ab: StageABOutput,
    stage_c: StageCOutput,
    stage_d: StageDOutput,
    language: str = "en",
) -> ModuleEvidenceOutput:
    bb_lookup = {node.id: node for node in cfg.bb_nodes}
    ab_lookup = {item.id: item for item in stage_ab.bb}
    selected_candidate = next((candidate for candidate in stage_c.candidates if candidate.id == stage_d.selected_candidate_id), None)
    selected_candidate_modules = {module.id: module for module in selected_candidate.mods} if selected_candidate else {}

    modules_payload: list[dict[str, Any]] = []
    for module_meta in stage_d.module_metadata:
        evidence_bb_ids = _resolve_evidence_bb_ids(module_meta, selected_candidate_modules)
        evidence_items: list[dict[str, Any]] = []
        for bb_id in evidence_bb_ids:
            node = bb_lookup.get(bb_id)
            if not node:
                continue
            evidence_items.append(
                {
                    "bb_id": bb_id,
                    "line_span": [node.start_line, node.end_line],
                    "signals": {
                        "calls": list(node.calls),
                        "defs": list(node.defs),
                        "uses": list(node.uses),
                        "effects": list(node.effects),
                        "kind": node.kind,
                    },
                }
            )

        review_flags = _build_review_flags(module_meta=module_meta, evidence_bb_ids=evidence_bb_ids, ab_lookup=ab_lookup, stage_d=stage_d)
        modules_payload.append(
            {
                "module_id": module_meta.module_id,
                "claim": {
                    "label": module_meta.label,
                    "desc": _claim_desc(module_meta, language),
                    "desc_status": module_meta.desc_status,
                    "confidence": module_meta.confidence,
                    "risk": module_meta.risk,
                },
                "evidence": evidence_items,
                "review_flags": review_flags,
            }
        )

    return ModuleEvidenceOutput(
        stage="module_evidence_v1",
        function_name=stage_d.function_name,
        module_evidence=modules_payload,
    )


def _resolve_evidence_bb_ids(module_meta: Any, selected_candidate_modules: dict[str, Any]) -> list[str]:
    if module_meta.evidence_bb_ids:
        return _unique_ordered([bb for bb in module_meta.evidence_bb_ids if bb in module_meta.bb_ids])

    candidate_module = selected_candidate_modules.get(module_meta.source_temp_module_id)
    if candidate_module and candidate_module.evi:
        return _unique_ordered([bb for bb in candidate_module.evi if bb in module_meta.bb_ids])

    return module_meta.bb_ids[: min(3, len(module_meta.bb_ids))]


def _claim_desc(module_meta: Any, language: str) -> str:
    if module_meta.desc_status == "invalidated":
        return tr(language, "fallback.invalidated_claim", label=module_meta.label.lower())
    return module_meta.desc


def _build_review_flags(
    *,
    module_meta: Any,
    evidence_bb_ids: list[str],
    ab_lookup: dict[str, Any],
    stage_d: StageDOutput,
) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []

    if module_meta.desc_status == "weakly_inherited":
        flags.append({"type": "weak_desc_inheritance", "severity": "M"})

    evidence_uncertainty = _highest_uncertainty(evidence_bb_ids, ab_lookup)
    if evidence_uncertainty == "H":
        flags.append({"type": "high_uncertainty_evidence", "severity": "H"})
    elif evidence_uncertainty == "M":
        flags.append({"type": "high_uncertainty_evidence", "severity": "M"})

    if _module_repair_heavy(module_meta=module_meta, stage_d=stage_d):
        flags.append({"type": "module_repair_heavy", "severity": "M"})

    return flags


def _highest_uncertainty(evidence_bb_ids: list[str], ab_lookup: dict[str, Any]) -> str | None:
    rank = {"L": 0, "M": 1, "H": 2}
    highest = None
    for bb_id in evidence_bb_ids:
        item = ab_lookup.get(bb_id)
        if not item:
            continue
        value = item.u
        if highest is None or rank.get(value, -1) > rank.get(highest, -1):
            highest = value
    return highest


def _module_repair_heavy(*, module_meta: Any, stage_d: StageDOutput) -> bool:
    tracked_types = {
        "merge_small_module",
        "resolve_duplicate_assignment",
        "assign_missing_bb",
        "repair_disconnected_module",
        "reduce_module_count",
    }
    source_id = module_meta.source_temp_module_id
    module_bb_ids = set(module_meta.bb_ids)

    for repair in stage_d.repairs:
        if repair.type not in tracked_types:
            continue
        if repair.bb_id and repair.bb_id in module_bb_ids:
            return True
        if repair.from_module and source_id != "N/A":
            owners = [part.strip() for part in repair.from_module.split(",") if part.strip()]
            if source_id in owners:
                return True
        if repair.to_module and source_id != "N/A" and repair.to_module == source_id:
            return True
    return False


def _unique_ordered(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
