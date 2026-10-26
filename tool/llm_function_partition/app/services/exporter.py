import json
from pathlib import Path
from typing import Any

from app.services.localization import normalize_language


def export_run_artifacts(
    output_dir: Path,
    cfg: dict[str, Any],
    partition: dict[str, str],
    module_graph: dict[str, Any],
    cfg_by_module: dict[str, Any],
    llm_debug: dict[str, Any],
    module_evidence: dict[str, Any] | None = None,
    stage_artifacts: dict[str, dict[str, Any]] | None = None,
    language: str = "en",
) -> None:
    language = normalize_language(language)
    output_dir.mkdir(parents=True, exist_ok=True)
    target_dir = output_dir / language
    target_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "latest_manifest.json", {"language": language, "path": str(target_dir)})
    _write_json(target_dir / "CFG.json", {**cfg, "language": language})
    _write_json(target_dir / "partition.json", partition)
    _write_json(target_dir / "module_graph.json", {**module_graph, "language": language})
    _write_json(target_dir / "cfg_by_module.json", cfg_by_module)
    _write_json(target_dir / "llm_debug.json", {**llm_debug, "language": language})
    if module_evidence is not None:
        _write_json(target_dir / "module_evidence.json", {**module_evidence, "language": language})
    if stage_artifacts:
        _cleanup_legacy_stage_files(target_dir)
        file_mapping = {
            "stage_ab": "stage_ab_global_bb.json",
            "stage_c": "stage_c_candidate_partition.json",
            "stage_d": "stage_d_verification_and_repair.json",
        }
        for stage_key, filename in file_mapping.items():
            payload = stage_artifacts.get(stage_key)
            if payload is not None:
                _write_json(target_dir / filename, {**payload, "language": language})


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _cleanup_legacy_stage_files(output_dir: Path) -> None:
    legacy_files = [
        "stage1_global_hypotheses.json",
        "stage2_bb_semantics.json",
        "stage3_pairwise_analysis.json",
        "stage4_verification_and_repair.json",
        "stage5_evidence_pack.json",
        "stage1_bb_semantics.json",
        "stage2_pairwise_analysis.json",
        "stage3_candidate_partitions.json",
        "module_audit.json",
        "audit_trail.json",
    ]
    for filename in legacy_files:
        path = output_dir / filename
        if path.exists():
            path.unlink()
