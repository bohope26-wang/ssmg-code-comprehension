from __future__ import annotations

import logging
from typing import Any

from app.services.graph_builder import build_cfg_by_module, build_module_graph
from app.services.localization import tr
from app.services.module_evidence import compile_module_evidence
from app.services.postprocess import verify_and_repair
from app.services.schemas import CFGPayload, RuntimeConfig
from app.services.stage_ab_global_bb import run_stage_ab_global_bb
from app.services.stage_c_partition import run_stage_c_partition


logger = logging.getLogger(__name__)


def run_multistage_pipeline(cfg: CFGPayload, runtime_config: RuntimeConfig) -> dict[str, Any]:
    logger.info("Multi-stage(v3 AB->C->D) start function=%s", runtime_config.function_name)
    stage_ab, stage_ab_debug = run_stage_ab_global_bb(cfg, runtime_config)
    stage_c, stage_c_debug = run_stage_c_partition(cfg, stage_ab, runtime_config)
    stage_d = verify_and_repair(cfg=cfg, stage_ab=stage_ab, stage_c=stage_c, runtime_config=runtime_config)
    module_evidence = compile_module_evidence(
        cfg=cfg,
        stage_ab=stage_ab,
        stage_c=stage_c,
        stage_d=stage_d,
        language=runtime_config.language,
    )

    bb_nodes = [node.model_dump(mode="json") for node in cfg.bb_nodes]
    cfg_edges = [edge.model_dump(mode="json", by_alias=True) for edge in cfg.cfg_edges]
    module_graph = build_module_graph(
        bb_nodes=bb_nodes,
        cfg_edges=cfg_edges,
        module_metadata=[
            {
                "module_id": item.module_id,
                "name": item.label,
                "description": item.desc,
                "bb_ids": item.bb_ids,
            }
            for item in stage_d.module_metadata
        ],
        partition=stage_d.final_partition,
    )
    cfg_by_module = build_cfg_by_module(bb_nodes=bb_nodes, cfg_edges=cfg_edges, partition=stage_d.final_partition)

    stage_outputs = {
        "stage_ab": stage_ab.model_dump(mode="json", by_alias=True),
        "stage_c": stage_c.model_dump(mode="json"),
        "stage_d": stage_d.model_dump(mode="json"),
    }
    debug_payload = {
        "mode": "multi_stage",
        "language": runtime_config.language,
        "runtime_config": runtime_config.model_dump(mode="json"),
        "warnings": stage_d.warnings,
        "function_summary": _build_function_summary(stage_ab, stage_d, runtime_config.language),
        "module_metadata": [
            {
                "module_id": item.module_id,
                "name": item.label,
                "description": item.desc,
                "bb_ids": item.bb_ids,
                "desc_status": item.desc_status,
                "source_temp_module_id": item.source_temp_module_id,
            }
            for item in stage_d.module_metadata
        ],
        "selected_candidate_id": stage_d.selected_candidate_id,
        "stage_debug": {"stage_ab": stage_ab_debug, "stage_c": stage_c_debug},
        "debug_flags": {
            "multi_candidates_debug": runtime_config.multi_candidates_debug,
        },
        "raw_response_text": "\n\n".join(
            [
                f"[stage_ab_global_bb]\n{stage_ab_debug.get('raw_response_text', '')}",
                f"[stage_c_candidate_partition]\n{stage_c_debug.get('raw_response_text', '')}",
            ]
        ).strip(),
    }
    logger.info(
        "Multi-stage(v3 AB->C->D) done function=%s modules=%s repairs=%s",
        runtime_config.function_name,
        len(stage_d.module_metadata),
        len(stage_d.repairs),
    )
    return {
        "cfg": {"function_source": cfg.function_source, "bb_nodes": bb_nodes, "cfg_edges": cfg_edges},
        "partition": stage_d.final_partition,
        "module_graph": module_graph,
        "cfg_by_module": cfg_by_module,
        "debug": debug_payload,
        "stage_outputs": stage_outputs,
        "module_evidence": module_evidence.model_dump(mode="json"),
    }


def _build_function_summary(stage_ab: Any, stage_d: Any, language: str) -> str:
    candidates = stage_ab.global_.function_summary_candidates if hasattr(stage_ab, "global_") else []
    if candidates and isinstance(candidates[0], list) and candidates[0]:
        return str(candidates[0][0])
    return tr(language, "fallback.verifier_selected", candidate_id=stage_d.selected_candidate_id)
