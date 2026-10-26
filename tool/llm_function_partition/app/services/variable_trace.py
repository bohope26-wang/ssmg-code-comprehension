from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.models import (
    VariableTraceEvent,
    VariableTraceExplainRequest,
    VariableTraceExplainResponse,
    VariableTraceRequest,
    VariableTraceResponse,
    VariableTraceStats,
)
from app.services.llm_json import call_llm_json
from app.services.localization import normalize_language, prompt_language_instruction, tr
from app.services.schemas import LLMConfig


logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "app" / "outputs"
TRACE_EVENT_ORDER = {"def": 0, "update": 1, "condition": 2, "output": 3, "use": 4}
UPDATE_METHODS = ("append", "extend", "update", "setdefault", "add", "remove", "pop", "clear", "sort", "reverse", "insert")
OUTPUT_HINTS = ("return", "yield", "dump", "write", "save", "persist", "send", "emit", "publish", "print")
IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def build_variable_trace(payload: VariableTraceRequest) -> VariableTraceResponse:
    language = normalize_language(payload.language)
    artifacts = _resolve_artifacts(payload, language)
    cfg = artifacts["cfg"]
    partition = artifacts["partition"]
    module_graph = artifacts["module_graph"]
    stage_outputs = artifacts["stage_outputs"]

    query = payload.variable_query.strip()
    if not query:
        raise ValueError(tr(language, "error.variable_query_empty"))

    bb_nodes = list(cfg.get("bb_nodes", []) or [])
    if not bb_nodes:
        raise ValueError(tr(language, "error.trace_no_cfg"))

    module_name_by_id = {
        str(module.get("id", "")).strip(): str(module.get("name", "")).strip()
        for module in module_graph.get("modules", []) or []
        if module.get("id")
    }
    module_desc_by_id = {
        str(item.get("module_id", "")).strip(): str(item.get("desc", "")).strip()
        for item in ((stage_outputs.get("stage_d") or {}).get("module_metadata", []) or [])
        if item.get("module_id")
    }

    match_counter: Counter[str] = Counter()
    primary_match_counter: Counter[str] = Counter()
    for node in bb_nodes:
        for symbol in _collect_matching_symbols(node, query):
            match_counter[symbol] += 1
            primary_match_counter[_symbol_root(symbol)] += 1

    if not match_counter:
        raise ValueError(tr(language, "error.variable_not_found", name=query))

    resolved_variable = _resolve_variable_name(query, match_counter, primary_match_counter)

    timeline: list[VariableTraceEvent] = []
    seen_definition = False
    for node in sorted(bb_nodes, key=_node_sort_key):
        event_types = _classify_node_events(node, resolved_variable, seen_definition)
        if "def" in event_types:
            seen_definition = True
        elif "update" in event_types and not seen_definition:
            seen_definition = True

        module_id = str(partition.get(node.get("id", ""), "")).strip() or None
        module_name = module_name_by_id.get(module_id or "", "") or module_desc_by_id.get(module_id or "", "") or None
        for event_type in sorted(event_types, key=lambda item: TRACE_EVENT_ORDER[item]):
            timeline.append(
                VariableTraceEvent(
                    module_id=module_id,
                    module_name=module_name,
                    bb_id=str(node.get("id", "")).strip(),
                    line_span=[node.get("start_line"), node.get("end_line")],
                    event_type=event_type,
                    code_snippet=str(node.get("code", "")).strip(),
                    reason=_build_event_reason(event_type, node, resolved_variable, language),
                )
            )

    if not timeline:
        raise ValueError(tr(language, "error.variable_no_events", name=resolved_variable))

    related_modules = _ordered_unique(item.module_id for item in timeline if item.module_id)
    bb_ids = _ordered_unique(item.bb_id for item in timeline if item.bb_id)
    line_spans = _ordered_unique(tuple(item.line_span) for item in timeline if any(value is not None for value in item.line_span))

    stats = VariableTraceStats(
        def_count=sum(1 for item in timeline if item.event_type == "def"),
        update_count=sum(1 for item in timeline if item.event_type == "update"),
        use_count=sum(1 for item in timeline if item.event_type == "use"),
        condition_count=sum(1 for item in timeline if item.event_type == "condition"),
        output_count=sum(1 for item in timeline if item.event_type == "output"),
        matched_bb_count=len(bb_ids),
        related_module_count=len(related_modules),
    )

    return VariableTraceResponse(
        language=language,
        function_name=payload.function_name,
        query=query,
        resolved_variable=resolved_variable,
        matches=[item for item, _ in match_counter.most_common()],
        role_hint=_infer_role_hint(stats, language),
        timeline=timeline,
        related_modules=related_modules,
        line_spans=[[start, end] for start, end in line_spans],
        bb_ids=bb_ids,
        trace_stats=stats,
    )


def explain_variable_trace(payload: VariableTraceExplainRequest) -> VariableTraceExplainResponse:
    language = normalize_language(payload.language)
    trace = payload.trace if isinstance(payload.trace, VariableTraceResponse) else VariableTraceResponse.model_validate(payload.trace)
    artifacts = _resolve_artifacts(payload, language)
    stage_outputs = artifacts["stage_outputs"]
    module_graph = artifacts["module_graph"]
    llm_config = LLMConfig.model_validate(payload.llm or {})

    module_metadata = {
        str(item.get("module_id", "")).strip(): item
        for item in ((stage_outputs.get("stage_d") or {}).get("module_metadata", []) or [])
        if item.get("module_id")
    }
    graph_edges = [
        edge
        for edge in (module_graph.get("edges", []) or [])
        if edge.get("from") in trace.related_modules or edge.get("to") in trace.related_modules
    ]

    prompt = _build_trace_explain_prompt(trace, module_metadata, graph_edges, language)
    schema_hint = {
        "role": tr(language, "trace.role.output_state"),
        "summary": tr(language, "trace.summary_role", name=trace.resolved_variable, role=tr(language, "trace.role.output_state"), function_name=payload.function_name),
        "key_transitions": [
            tr(language, "trace.transition.initialized"),
            tr(language, "trace.transition.updated"),
            tr(language, "trace.transition.output"),
        ],
        "impact": [
            tr(language, "trace.impact_output", count=1),
            tr(language, "trace.impact_modules", modules=", ".join(trace.related_modules[:2] or ["M1"])),
        ],
    }

    try:
        llm_result = call_llm_json(
            prompt=prompt,
            model=payload.model,
            temperature=payload.temperature,
            stage_name="variable_trace_explain",
            schema_hint=schema_hint,
            llm_config=llm_config,
            max_format_retries=llm_config.max_format_retries,
            language=language,
        )
        repaired = _repair_trace_explain_payload(llm_result.parsed_json, trace, language)
        return VariableTraceExplainResponse(
            language=language,
            function_name=payload.function_name,
            query=trace.query,
            resolved_variable=trace.resolved_variable,
            generation_mode="llm",
            warning=None,
            role=repaired["role"],
            summary=repaired["summary"],
            key_transitions=repaired["key_transitions"],
            impact=repaired["impact"],
        )
    except RuntimeError as exc:
        logger.warning("Variable trace explanation fallback function=%s variable=%s error=%s", payload.function_name, trace.resolved_variable, exc)
        fallback = _fallback_trace_explanation(trace, module_metadata, language)
        return VariableTraceExplainResponse(
            language=language,
            function_name=payload.function_name,
            query=trace.query,
            resolved_variable=trace.resolved_variable,
            generation_mode="fallback",
            warning=str(exc),
            role=fallback["role"],
            summary=fallback["summary"],
            key_transitions=fallback["key_transitions"],
            impact=fallback["impact"],
        )


def _resolve_artifacts(payload: Any, language: str) -> dict[str, Any]:
    cfg = payload.cfg if getattr(payload, "cfg", None) else _load_output_json("CFG.json", language)
    partition = payload.partition if getattr(payload, "partition", None) else _load_output_json("partition.json", language)
    module_graph = payload.module_graph if getattr(payload, "module_graph", None) else _load_output_json("module_graph.json", language)
    cfg_by_module = payload.cfg_by_module if getattr(payload, "cfg_by_module", None) else _load_output_json("cfg_by_module.json", language)
    module_evidence = payload.module_evidence if getattr(payload, "module_evidence", None) else _load_output_json("module_evidence.json", language)
    stage_outputs = payload.stage_outputs if getattr(payload, "stage_outputs", None) else {
        "stage_ab": _load_output_json("stage_ab_global_bb.json", language),
        "stage_c": _load_output_json("stage_c_candidate_partition.json", language),
        "stage_d": _load_output_json("stage_d_verification_and_repair.json", language),
    }
    return {
        "cfg": cfg or {},
        "partition": partition or {},
        "module_graph": module_graph or {},
        "cfg_by_module": cfg_by_module or {},
        "module_evidence": module_evidence or {},
        "stage_outputs": stage_outputs or {},
    }


def _load_output_json(filename: str, language: str) -> dict[str, Any]:
    language = normalize_language(language)
    path = OUTPUT_DIR / language / filename
    if not path.exists() and language == "en":
        path = OUTPUT_DIR / filename
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(tr(language, "error.artifact_parse_failed", filename=filename, error=exc)) from exc


def _resolve_variable_name(query: str, match_counter: Counter[str], primary_match_counter: Counter[str]) -> str:
    normalized_query = query.strip().lower()
    exact = [
        item
        for item in primary_match_counter
        if item.lower() == normalized_query
    ]
    if exact:
        return sorted(exact, key=lambda item: (-primary_match_counter[item], item))[0]
    return primary_match_counter.most_common(1)[0][0]


def _collect_matching_symbols(node: dict[str, Any], query: str) -> list[str]:
    query_lower = query.strip().lower()
    symbols = _node_symbols(node)
    exact_matches = [symbol for symbol in symbols if _matches_query(symbol, query_lower, mode="exact")]
    if exact_matches:
        return exact_matches
    return [symbol for symbol in symbols if _matches_query(symbol, query_lower, mode="fuzzy")]


def _node_symbols(node: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("defs", "uses"):
        for item in node.get(key, []) or []:
            text = str(item).strip()
            if text:
                values.append(text)
    return values


def _matches_query(symbol: str, query_lower: str, *, mode: str) -> bool:
    symbol_lower = symbol.lower()
    root = _symbol_root(symbol).lower()
    if mode == "exact":
        return symbol_lower == query_lower or root == query_lower
    return query_lower in symbol_lower or query_lower in root or symbol_lower in query_lower or root in query_lower


def _symbol_root(symbol: str) -> str:
    match = IDENTIFIER_RE.search(symbol or "")
    return match.group(0) if match else str(symbol or "").strip()


def _classify_node_events(node: dict[str, Any], resolved_variable: str, seen_definition: bool) -> list[str]:
    code = str(node.get("code", "")).strip()
    defs = [_symbol_root(item) for item in node.get("defs", []) or []]
    uses = [_symbol_root(item) for item in node.get("uses", []) or []]
    query = resolved_variable

    has_def = query in defs
    has_use = query in uses or _code_mentions_variable(code, query)
    has_update = _is_update_event(code, query)
    has_condition = _is_condition_event(node, code, query, has_use)
    has_output = _is_output_event(node, code, query, has_use)

    events: list[str] = []
    if has_def:
        events.append("update" if seen_definition else "def")
    elif has_update:
        events.append("update" if seen_definition else "def")

    if has_condition:
        events.append("condition")
    if has_output:
        events.append("output")
    if has_use and not events:
        events.append("use")
    return events


def _code_mentions_variable(code: str, variable: str) -> bool:
    if not code:
        return False
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(variable)}(?![A-Za-z0-9_])", code) is not None


def _is_update_event(code: str, variable: str) -> bool:
    if not _code_mentions_variable(code, variable):
        return False
    assign_patterns = (
        rf"^\s*{re.escape(variable)}\s*[:+*/%\-]*=",
        rf"^\s*{re.escape(variable)}\[[^\]]+\]\s*=",
        rf"^\s*{re.escape(variable)}\.[A-Za-z_][A-Za-z0-9_]*\s*=",
    )
    if any(re.search(pattern, code) for pattern in assign_patterns):
        return True
    if any(re.search(rf"{re.escape(variable)}\.{method}\s*\(", code) for method in UPDATE_METHODS):
        return True
    return False


def _is_condition_event(node: dict[str, Any], code: str, variable: str, has_use: bool) -> bool:
    kind = str(node.get("kind", "")).strip().lower()
    if kind == "condition" and has_use:
        return True
    if re.match(r"^(if|elif|while|assert)\b", code):
        return _code_mentions_variable(code, variable)
    return False


def _is_output_event(node: dict[str, Any], code: str, variable: str, has_use: bool) -> bool:
    lowered = code.lower()
    if lowered.startswith("return ") and _code_mentions_variable(code, variable):
        return True
    if lowered.startswith("yield ") and _code_mentions_variable(code, variable):
        return True
    if not has_use:
        return False
    if any(effect for effect in node.get("effects", []) or []):
        return True
    return any(re.search(rf"\b{hint}[A-Za-z_]*\b", lowered) for hint in OUTPUT_HINTS)


def _build_event_reason(event_type: str, node: dict[str, Any], resolved_variable: str, language: str) -> str:
    del node
    if event_type == "def":
        return tr(language, "trace.event.def", name=resolved_variable)
    if event_type == "update":
        return tr(language, "trace.event.update", name=resolved_variable)
    if event_type == "condition":
        return tr(language, "trace.event.condition", name=resolved_variable)
    if event_type == "output":
        return tr(language, "trace.event.output", name=resolved_variable)
    return tr(language, "trace.event.use", name=resolved_variable)


def _node_sort_key(node: dict[str, Any]) -> tuple[int, int]:
    line = node.get("start_line")
    if isinstance(line, int):
        return (line, _bb_numeric_id(node.get("id", "")))
    return (10**9, _bb_numeric_id(node.get("id", "")))


def _bb_numeric_id(bb_id: str) -> int:
    match = re.search(r"(\d+)", str(bb_id))
    return int(match.group(1)) if match else 10**9


def _ordered_unique(values: Any) -> list[Any]:
    seen: set[Any] = set()
    ordered: list[Any] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _infer_role_hint(stats: VariableTraceStats, language: str) -> str:
    if stats.output_count > 0 and (stats.def_count + stats.update_count) > 0:
        return tr(language, "trace.role.output_state")
    if stats.condition_count >= max(1, stats.def_count) and stats.update_count <= 1:
        return tr(language, "trace.role.control_flag")
    if stats.update_count >= 2:
        return tr(language, "trace.role.state_accumulator")
    if stats.def_count == 0 and stats.use_count > 0:
        return tr(language, "trace.role.input_dependency")
    return tr(language, "trace.role.working_state")


def _build_trace_explain_prompt(
    trace: VariableTraceResponse,
    module_metadata: dict[str, dict[str, Any]],
    graph_edges: list[dict[str, Any]],
    language: str,
) -> str:
    related_module_payload = {
        module_id: module_metadata[module_id]
        for module_id in trace.related_modules
        if module_id in module_metadata
    }
    timeline_payload = [item.model_dump(mode="json") for item in trace.timeline[:32]]
    return f"""
You are writing a concise variable-understanding summary for one Python function.
{prompt_language_instruction(language)}

Rules:
- Do not search for new trace facts.
- Only explain the existing trace timeline.
- Keep the tone concrete and analytical.
- Return one JSON object only.
- No markdown fences and no extra commentary.
- Natural-language values in `role`, `summary`, `key_transitions`, and `impact` must follow the language requirement above.

Trace summary:
{json.dumps(trace.model_dump(mode="json"), ensure_ascii=False, indent=2)}

Relevant module metadata:
{json.dumps(related_module_payload, ensure_ascii=False, indent=2)}

Relevant module graph edges:
{json.dumps(graph_edges, ensure_ascii=False, indent=2)}

Focus especially on:
- what role the variable plays in the function
- where it is initialized or updated
- where it affects control flow
- whether it becomes part of the final output or side effects

Return JSON with this shape:
{{
  "role": {json.dumps(tr(language, "trace.role.output_state"), ensure_ascii=False)},
  "summary": {json.dumps(tr(language, "trace.summary_role", name=trace.resolved_variable, role=tr(language, "trace.role.output_state"), function_name=trace.function_name), ensure_ascii=False)},
  "key_transitions": [
    {json.dumps(tr(language, "trace.transition.initialized"), ensure_ascii=False)},
    {json.dumps(tr(language, "trace.transition.updated"), ensure_ascii=False)},
    {json.dumps(tr(language, "trace.transition.output"), ensure_ascii=False)}
  ],
  "impact": [
    {json.dumps(tr(language, "trace.impact_output", count=1), ensure_ascii=False)},
    {json.dumps(tr(language, "trace.impact_modules", modules=", ".join(trace.related_modules[:2] or ["M1"])), ensure_ascii=False)}
  ]
}}

Use the timeline below as the primary evidence:
{json.dumps(timeline_payload, ensure_ascii=False, indent=2)}
"""


def _repair_trace_explain_payload(parsed: dict[str, Any], trace: VariableTraceResponse, language: str) -> dict[str, Any]:
    fallback = _fallback_trace_explanation(trace, {}, language)
    role = _clean_short_text(parsed.get("role"), fallback["role"])
    summary = _clean_short_text(parsed.get("summary"), fallback["summary"], limit_words=80)
    key_transitions = _clean_text_list(parsed.get("key_transitions"), fallback["key_transitions"])
    impact = _clean_text_list(parsed.get("impact"), fallback["impact"])
    return {
        "role": role,
        "summary": summary,
        "key_transitions": key_transitions,
        "impact": impact,
    }


def _fallback_trace_explanation(
    trace: VariableTraceResponse,
    module_metadata: dict[str, dict[str, Any]],
    language: str,
) -> dict[str, Any]:
    def_event = next((item for item in trace.timeline if item.event_type == "def"), None)
    update_event = next((item for item in trace.timeline if item.event_type == "update"), None)
    condition_event = next((item for item in trace.timeline if item.event_type == "condition"), None)
    output_event = next((item for item in trace.timeline if item.event_type == "output"), None)

    transitions: list[str] = []
    if def_event:
        transitions.append(_event_transition_text(tr(language, "trace.transition.initialized"), def_event, module_metadata, language))
    if update_event:
        transitions.append(_event_transition_text(tr(language, "trace.transition.updated"), update_event, module_metadata, language))
    if condition_event:
        transitions.append(_event_transition_text(tr(language, "trace.transition.condition"), condition_event, module_metadata, language))
    if output_event:
        transitions.append(_event_transition_text(tr(language, "trace.transition.output"), output_event, module_metadata, language))
    if not transitions:
        transitions.append(
            tr(
                language,
                "trace.fallback_transition",
                name=trace.resolved_variable,
                count=max(1, trace.trace_stats.related_module_count),
            )
        )

    impact: list[str] = []
    if trace.trace_stats.output_count > 0:
        impact.append(tr(language, "trace.impact_output", count=trace.trace_stats.output_count))
    if trace.trace_stats.condition_count > 0:
        impact.append(tr(language, "trace.impact_condition", count=trace.trace_stats.condition_count))
    if trace.related_modules:
        impact.append(tr(language, "trace.impact_modules", modules=", ".join(trace.related_modules[:4])))
    if not impact:
        impact.append(tr(language, "trace.impact_local", function_name=trace.function_name))

    role = trace.role_hint
    summary_parts = [tr(language, "trace.summary_role", name=trace.resolved_variable, role=role, function_name=trace.function_name)]
    if def_event:
        summary_parts.append(
            tr(
                language,
                "trace.summary_first_line",
                line=def_event.line_span[0] or "?",
                module=def_event.module_id or ("the current flow" if language == "en" else "当前流程"),
            )
        )
    if output_event:
        summary_parts.append(tr(language, "trace.summary_output"))
    elif update_event:
        summary_parts.append(tr(language, "trace.summary_update"))

    return {
        "role": role,
        "summary": " ".join(summary_parts),
        "key_transitions": transitions[:4],
        "impact": impact[:4],
    }


def _event_transition_text(prefix: str, event: VariableTraceEvent, module_metadata: dict[str, dict[str, Any]], language: str) -> str:
    module_id = event.module_id or tr(language, "trace.unknown_module")
    module_label = module_metadata.get(module_id, {}).get("label") or event.module_name or module_id
    start_line = event.line_span[0] if event.line_span else None
    if start_line:
        return tr(language, "trace.transition_text", prefix=prefix, module=module_label, line=start_line)
    return tr(language, "trace.transition_text_no_line", prefix=prefix, module=module_label)


def _clean_short_text(value: Any, fallback: str, *, limit_words: int = 12) -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    text = re.sub(r"\s+", " ", text)
    words = text.split()
    if len(words) > limit_words:
        text = " ".join(words[:limit_words])
    return text


def _clean_text_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    cleaned: list[str] = []
    for item in value:
        text = _clean_short_text(item, "", limit_words=24)
        if text:
            cleaned.append(text)
    return cleaned[:4] if cleaned else fallback
