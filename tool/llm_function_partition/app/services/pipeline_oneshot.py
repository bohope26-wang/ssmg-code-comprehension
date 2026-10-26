from __future__ import annotations

import logging
from typing import Any

from app.services.graph_builder import build_cfg_by_module, build_module_graph
from app.services.llm_json import call_llm_json
from app.services.partitioner import normalize_partition_result
from app.services.prompt_builder import build_partition_prompt, one_shot_schema_hint
from app.services.schemas import CFGPayload, RuntimeConfig


logger = logging.getLogger(__name__)


def run_oneshot_pipeline(cfg: CFGPayload, runtime_config: RuntimeConfig) -> dict[str, Any]:
    logger.info("One-shot pipeline start function=%s", runtime_config.function_name)
    bb_nodes = [node.model_dump(mode="json") for node in cfg.bb_nodes]
    cfg_edges = [edge.model_dump(mode="json", by_alias=True) for edge in cfg.cfg_edges]

    prompt = build_partition_prompt(
        source_code=cfg.function_source,
        function_name=runtime_config.function_name,
        bb_nodes=bb_nodes,
        cfg_edges=cfg_edges,
        max_modules=runtime_config.max_modules,
        language=runtime_config.language,
    )
    schema_hint = one_shot_schema_hint(runtime_config.language)
    llm_result = call_llm_json(
        prompt=prompt,
        model=runtime_config.model,
        temperature=runtime_config.temperature,
        stage_name="one_shot",
        schema_hint=schema_hint,
        llm_config=runtime_config.llm,
        max_format_retries=1,
        language=runtime_config.language,
    )
    normalized = normalize_partition_result(
        parsed_response=llm_result.parsed_json,
        bb_nodes=bb_nodes,
        language=runtime_config.language,
    )
    module_graph = build_module_graph(
        bb_nodes=bb_nodes,
        cfg_edges=cfg_edges,
        module_metadata=normalized.module_metadata,
        partition=normalized.partition,
    )
    cfg_by_module = build_cfg_by_module(
        bb_nodes=bb_nodes,
        cfg_edges=cfg_edges,
        partition=normalized.partition,
    )
    debug_payload = {
        "mode": "one_shot",
        "language": runtime_config.language,
        "prompt": prompt,
        "raw_response_text": llm_result.raw_response_text,
        "parsed_response": llm_result.parsed_json,
        "warnings": normalized.warnings,
        "function_summary": normalized.function_summary,
        "module_metadata": normalized.module_metadata,
        "attempts": llm_result.attempts,
    }
    logger.info("One-shot pipeline done function=%s modules=%s", runtime_config.function_name, len(module_graph["modules"]))
    return {
        "cfg": {"function_source": cfg.function_source, "bb_nodes": bb_nodes, "cfg_edges": cfg_edges},
        "partition": normalized.partition,
        "module_graph": module_graph,
        "cfg_by_module": cfg_by_module,
        "debug": debug_payload,
        "stage_outputs": {},
        "module_evidence": None,
    }
