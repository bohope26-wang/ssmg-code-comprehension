from __future__ import annotations

import json
import logging
from typing import Any

from app.services.llm_json import LLMJsonCallResult, call_llm_json
from app.services.localization import prompt_language_instruction, tr
from app.services.schemas import CFGPayload, RuntimeConfig, StageABOutput


logger = logging.getLogger(__name__)


def run_stage_ab_global_bb(cfg: CFGPayload, runtime_config: RuntimeConfig) -> tuple[StageABOutput, dict[str, Any]]:
    logger.info("StageAB start function=%s bb_count=%s", runtime_config.function_name, len(cfg.bb_nodes))
    prompt = _build_stage_ab_prompt(cfg=cfg, runtime_config=runtime_config)
    schema_hint = {
        "stage": "stage_ab_global_bb_v1",
        "function_name": runtime_config.function_name,
        "global": {
            "function_summary_candidates": [[tr(runtime_config.language, "fallback.function_summary"), 61]],
            "workflow_hypotheses": [
                [
                    "H1",
                    [
                        tr(runtime_config.language, "fallback.workflow_setup"),
                        tr(runtime_config.language, "fallback.workflow_validation"),
                        tr(runtime_config.language, "fallback.workflow_compute"),
                        tr(runtime_config.language, "fallback.workflow_return"),
                    ],
                    58,
                ]
            ],
            "coarse_boundary_hints": [[["BB1", "BB2"], 64]],
            "uncertain_regions": [[["BB3", "BB4"], "M"]],
        },
        "bb": [
            {
                "id": "BB1",
                "cr": "guard",
                "rc": [
                    [tr(runtime_config.language, "fallback.workflow_validation"), 67],
                    [tr(runtime_config.language, "label.unknown"), 33],
                ],
                "u": "L",
            }
        ],
    }

    llm_result: LLMJsonCallResult | None = None
    stage_error = ""
    try:
        llm_result = call_llm_json(
            prompt=prompt,
            model=runtime_config.model_for_stage("ab"),
            temperature=runtime_config.temperature,
            stage_name="stage_ab_global_bb",
            schema_hint=schema_hint,
            llm_config=runtime_config.llm,
            max_format_retries=runtime_config.llm.max_format_retries,
            language=runtime_config.language,
        )
        parsed = llm_result.parsed_json
    except RuntimeError as exc:
        logger.warning("StageAB failed; fallback to deterministic seed error=%s", exc)
        parsed = {}
        stage_error = str(exc)

    repaired = _repair_stage_ab_payload(parsed=parsed, cfg=cfg, runtime_config=runtime_config)
    stage_ab = StageABOutput.model_validate(repaired)
    debug = {
        "prompt": prompt,
        "language": runtime_config.language,
        "raw_response_text": llm_result.raw_response_text if llm_result else "",
        "parsed_response": llm_result.parsed_json if llm_result else {},
        "attempts": llm_result.attempts if llm_result else 0,
        "error": stage_error,
    }
    logger.info("StageAB done function=%s bb_items=%s", runtime_config.function_name, len(stage_ab.bb))
    return stage_ab, debug


def _build_stage_ab_prompt(cfg: CFGPayload, runtime_config: RuntimeConfig) -> str:
    cfg_payload = cfg.model_dump(mode="json", by_alias=True)
    function_name = runtime_config.function_name
    validation_label = tr(runtime_config.language, "fallback.workflow_validation")
    compute_label = tr(runtime_config.language, "fallback.workflow_compute")
    unknown_label = tr(runtime_config.language, "label.unknown")

    return f"""You are partitioning one Python function into semantic modules at the basic-block level.
You are Stage AB (single call): global weak hypotheses + BB local semantic skeleton.
{prompt_language_instruction(runtime_config.language)}

Your job is to analyze one Python function and produce:
1. global weak hypotheses about the function as a whole
2. a local semantic skeleton for each basic block (BB)

IMPORTANT:
- Output one JSON object only
- No markdown fences
- No explanations outside JSON
- Keep output compact
- Do NOT output final module partition
- Do NOT assign final modules
- The `global` section is advisory weak prior only, not final truth
- `global.uncertain_regions` must always exist
- For each BB in the input, output exactly one item in `bb`

==================================================
[Boundary and granularity rules]

Use these rules when creating workflow hypotheses, coarse boundary hints, and BB semantic roles.
They guide later module partitioning, but Stage AB still must NOT output a final partition.

Prefer boundary hints where:
1. The semantic goal changes, such as input normalization to core computation, or candidate construction to result aggregation.
2. The main operation target changes, such as database collections to fields, provider to room, or ledger to bank.
3. The key intermediate artifact changes, such as `allowed_len`, `uri`, `array`, `decision`, `schedule`, `alerts`, or `partition`.
4. The flow enters mutually exclusive main branches or independent processing paths, such as sparse/dense, zip/tar, streamed/non-streamed, or receive/reserve/ship.
5. A group of validations shares one error meaning or jointly serves the same later stage; treat that group as one semantic phase.
6. A single-line `return` usually belongs to the previous semantic phase; only entry short-circuit returns or branch short-circuit returns should be treated as separate phase candidates.

Do NOT create boundary hints merely because of:
1. multi-line function calls, dictionary literals, list comprehensions, or string concatenation
2. several consecutive `if` checks under the same local goal
3. comments or docstrings
4. small temporary assignments that only serve the next step
5. small updates inside one loop body that all serve the same accumulated state

Granularity:
- `max_modules` is {runtime_config.max_modules}, and it is only an upper bound for the later final partition.
- Short functions(below 50 lines) usually need 4-6 modules.
- Medium functions(50 lines to 110 lines) usually need 6-8 modules.
- Long functions(more than 110 lines) usually need 7-9 modules.
- Module counts do not need to be equal across functions.
- Prefer complete semantic phases and explainable boundaries over matching any fixed module count.
- If the function is too small to support the usual range, use fewer meaningful phases.

==================================================
FIELD SEMANTICS

You must follow these meanings strictly.

[Top-level fields]

- `stage`:
  Fixed string: `"stage_ab_global_bb_v1"`.

- `function_name`:
  Copy the provided function name exactly.

- `global`:
  Function-level weak hypotheses.
  This section gives coarse understanding of the whole function.
  It must NOT be treated as final partitioning output.

- `bb`:
  A list of BB-level local semantic skeletons.
  There must be exactly one item for every BB in the input.

==================================================
[Meaning of fields inside `global`]

1. `function_summary_candidates`
Meaning:
- Short whole-function summaries.
- They describe what the function is broadly doing end-to-end.
- These are global summaries, not module labels.

How to fill:
- Provide 1 to 2 candidates only.
- Each item is:
  ["summary text", confidence]
- `summary text` must be short, concrete, and action-oriented.
- `confidence` is an integer from 0 to 100.

Do NOT:
- Do not describe individual BBs one by one.
- Do not simply restate the function name.
- Do not output vague text like "handles logic" or "processes data".

2. `workflow_hypotheses`
Meaning:
- Coarse possible phase sequences of the function.
- These are human-readable workflow guesses, not final module outputs.

How to fill:
- Provide 1 to 2 hypotheses only.
- Each item is:
  ["H1", ["Setup", "Validation", "Compute", "Persist"], confidence]
- Phase names must be short, generic, reusable process labels.
- The number of phase names should follow the granularity rules above: short functions usually 4-6, medium functions usually 6-8, long functions usually 7-9, and fewer if the code has fewer meaningful stages.
- Use likely execution order.

Do NOT:
- Do not use overly specific business phrases as phase names.
- Do not create too many phases.
- Do not force every function into the same phase template.

3. `coarse_boundary_hints`
Meaning:
- Weak hints about where a coarse semantic transition may occur.
- These are possible module boundary locations, not final boundaries.

How to fill:
- Each item is:
  [[from_bb_id, to_bb_id], confidence]
- Only include a small number of strong hints.
- Use this when there is a likely transition of role, phase, or effect.

Do NOT:
- Do not mark many edges.
- Do not treat every branch edge as a boundary.
- Do not use this as final cut decisions.

4. `uncertain_regions`
Meaning:
- Regions where the model is not confident about the global interpretation.
- These usually correspond to mixed-responsibility, transitional, or semantically ambiguous areas.
- This field is required because later stages must know where not to trust Stage AB too much.

How to fill:
- Each item is:
  [[bb_id_1, bb_id_2, ...], "L" | "M" | "H"]
- Use "L" for mild uncertainty, "M" for medium uncertainty, "H" for high uncertainty.
- If only one BB is uncertain, use a one-element list.

Do NOT:
- Do not leave this field out.
- Do not mark everything uncertain.
- Do not mark nothing uncertain unless the function is genuinely very simple and clear.

==================================================
[Meaning of fields inside `bb`]

Each item in `bb` must correspond to exactly one BB.

1. `id`
Meaning:
- The BB id from the input CFG.
- Copy exactly.

2. `cr`
Meaning:
- Control-role of the BB.
- This is about structural role in control flow, NOT business meaning.

Allowed values:
- "setup"
- "guard"
- "branch_body"
- "loop_header"
- "loop_body"
- "compute"
- "side_effect"
- "return"
- "exception"
- "cleanup"
- "unknown"

How to choose:
- Use the role that best describes how the BB behaves in control flow.

Do NOT:
- Do not use semantic labels like Validation / Persist here.
- Do not invent new values.

3. `rc`
Meaning:
- Role candidates for the BB at the semantic responsibility level.
- This is about what the BB is likely doing semantically.
- Unlike `cr`, this is not control-flow structure, but semantic function.

How to fill:
- Each item is:
  ["role_name", score]
- Provide 2 to 4 candidates.
- Scores must be integers from 0 to 100.
- Scores should roughly reflect relative likelihood.
- Typical role names include:
  "Setup", "Validation", "Compute", "Transform", "Persist", "Notify", "ErrorHandling", "Cleanup", "Unknown"

Do NOT:
- Do not give only one candidate.
- Do not use `cr` labels directly unless truly appropriate.
- Do not output long explanations inside `rc`.

4. `u`
Meaning:
- Uncertainty of the BB-level semantic judgment.

Allowed values:
- "L" = low uncertainty
- "M" = medium uncertainty
- "H" = high uncertainty

How to choose:
- Use "L" when one interpretation is clearly dominant.
- Use "M" when there is some ambiguity.
- Use "H" when the BB looks transitional, mixed, or hard to interpret.

==================================================
[Key distinction you must follow]

- `cr` = control-flow role
  Example: guard / loop_header / return
- `rc` = semantic responsibility candidates
  Example: Validation / Compute / Persist

They are NOT the same thing.
Do not confuse them.

==================================================
[Output style constraints]

- Keep all texts compact
- Use integers for confidence / scores
- Prefer short phrases
- No extra keys
- No comments
- No nulls unless absolutely necessary
- Natural-language values in `global.*` and `bb[*].rc[*][0]` must follow the language requirement above.

==================================================
Function name:
{function_name}

CFG.json:
{json.dumps(cfg_payload, ensure_ascii=False, indent=2)}

Output schema:
{{
  "stage": "stage_ab_global_bb_v1",
  "function_name": "{function_name}",
  "global": {{
    "function_summary_candidates": [[{json.dumps(tr(runtime_config.language, "fallback.function_summary"), ensure_ascii=False)}, 61]],
    "workflow_hypotheses": [["H1", [{json.dumps(validation_label, ensure_ascii=False)}, {json.dumps(compute_label, ensure_ascii=False)}], 58]],
    "coarse_boundary_hints": [[["BB3", "BB4"], 64]],
    "uncertain_regions": [[["BB8", "BB9"], "M"]]
  }},
  "bb": [
    {{
      "id": "BB3",
      "cr": "guard",
      "rc": [[{json.dumps(validation_label, ensure_ascii=False)}, 67], [{json.dumps(compute_label, ensure_ascii=False)}, 18], [{json.dumps(unknown_label, ensure_ascii=False)}, 15]],
      "u": "L"
    }}
  ]
}}
"""


def _repair_stage_ab_payload(*, parsed: dict[str, Any], cfg: CFGPayload, runtime_config: RuntimeConfig) -> dict[str, Any]:
    valid_bb_ids = [node.id for node in cfg.bb_nodes]
    valid_set = set(valid_bb_ids)
    language = runtime_config.language

    global_raw = parsed.get("global", {}) if isinstance(parsed, dict) else {}
    function_summary_candidates = _repair_summary_candidates(global_raw.get("function_summary_candidates"), language)
    workflow_hypotheses = _repair_workflow_hypotheses(global_raw.get("workflow_hypotheses"), language)
    coarse_boundary_hints = _repair_boundary_hints(global_raw.get("coarse_boundary_hints"), valid_set)
    uncertain_regions = _repair_uncertain_regions(global_raw.get("uncertain_regions"), valid_bb_ids)

    bb_raw = parsed.get("bb", []) if isinstance(parsed, dict) else []
    by_id: dict[str, dict[str, Any]] = {}
    if isinstance(bb_raw, list):
        for item in bb_raw:
            if isinstance(item, dict) and str(item.get("id", "")).strip():
                by_id[str(item["id"]).strip()] = item

    bb_items: list[dict[str, Any]] = []
    for node in cfg.bb_nodes:
        raw = by_id.get(node.id, {})
        bb_items.append(
            {
                "id": node.id,
                "cr": _normalize_cr(raw.get("cr"), node),
                "rc": _repair_role_candidates(raw.get("rc"), node, language),
                "u": _normalize_uncertainty(raw.get("u")),
            }
        )

    return {
        "stage": "stage_ab_global_bb_v1",
        "function_name": runtime_config.function_name,
        "global": {
            "function_summary_candidates": function_summary_candidates,
            "workflow_hypotheses": workflow_hypotheses,
            "coarse_boundary_hints": coarse_boundary_hints,
            "uncertain_regions": uncertain_regions,
        },
        "bb": bb_items,
    }


def _repair_summary_candidates(value: Any, language: str) -> list[list[Any]]:
    rows: list[list[Any]] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, list) and len(item) >= 2:
                text = str(item[0]).strip()[:220]
                score = _clip_percent(item[1], default=50)
                if text:
                    rows.append([text, score])
    if not rows:
        rows = [[tr(language, "fallback.function_summary"), 45]]
    return rows[:4]


def _repair_workflow_hypotheses(value: Any, language: str) -> list[list[Any]]:
    rows: list[list[Any]] = []
    if isinstance(value, list):
        for idx, item in enumerate(value, start=1):
            if not isinstance(item, list) or len(item) < 3:
                continue
            hid = str(item[0]).strip() or f"H{idx}"
            phases_raw = item[1]
            conf_raw = item[2]
            phases = [str(phase).strip()[:40] for phase in phases_raw if str(phase).strip()] if isinstance(phases_raw, list) else []
            if not phases:
                continue
            rows.append([hid, phases[:8], _clip_percent(conf_raw, default=50)])
    if not rows:
        rows = [
            [
                "H1",
                [
                    tr(language, "fallback.workflow_setup"),
                    tr(language, "fallback.workflow_validation"),
                    tr(language, "fallback.workflow_compute"),
                    tr(language, "fallback.workflow_return"),
                ],
                45,
            ]
        ]
    return rows[:4]


def _repair_boundary_hints(value: Any, valid_ids: set[str]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, list) or len(item) < 2:
                continue
            between = item[0]
            conf_raw = item[1]
            if not isinstance(between, list) or len(between) != 2:
                continue
            bb1 = str(between[0]).strip()
            bb2 = str(between[1]).strip()
            if bb1 not in valid_ids or bb2 not in valid_ids or bb1 == bb2:
                continue
            rows.append([[bb1, bb2], _clip_percent(conf_raw, default=50)])
    return rows[:64]


def _repair_uncertain_regions(value: Any, valid_bb_ids: list[str]) -> list[list[Any]]:
    valid_set = set(valid_bb_ids)
    rows: list[list[Any]] = []
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, list) or len(item) < 2:
                continue
            bbs_raw = item[0]
            sev_raw = item[1]
            if not isinstance(bbs_raw, list):
                continue
            bbs = [str(bb).strip() for bb in bbs_raw if str(bb).strip() in valid_set]
            if not bbs:
                continue
            rows.append([list(dict.fromkeys(bbs))[:12], _normalize_uncertainty(sev_raw)])
    if not rows:
        fallback = [valid_bb_ids[min(len(valid_bb_ids) // 2, len(valid_bb_ids) - 1)]] if valid_bb_ids else []
        rows = [[fallback, "M"]]
    return rows[:12]


def _normalize_cr(value: Any, node: Any) -> str:
    allowed = {
        "setup",
        "guard",
        "branch_body",
        "loop_header",
        "loop_body",
        "compute",
        "side_effect",
        "return",
        "exception",
        "cleanup",
        "unknown",
    }
    text = str(value or "").strip()
    if text in allowed:
        return text
    kind = str(getattr(node, "kind", "")).lower()
    code = str(getattr(node, "code", ""))
    if "loop" in kind:
        return "loop_header"
    if kind in {"if", "condition"}:
        return "guard"
    if "return" in code or kind == "exit":
        return "return"
    if "raise" in code:
        return "exception"
    if getattr(node, "effects", []):
        return "side_effect"
    return "compute"


def _repair_role_candidates(value: Any, node: Any, language: str) -> list[list[Any]]:
    rows: list[list[Any]] = []
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, list) or len(item) < 2:
                continue
            role = str(item[0]).strip()[:48]
            if not role:
                continue
            score = _clip_percent(item[1], default=0)
            rows.append([role, score])
    if not rows:
        primary = _infer_primary_role(node, language)
        rows = [[primary, 70], [tr(language, "label.unknown"), 30]]

    dedup: dict[str, int] = {}
    for role, score in rows:
        dedup[str(role)] = max(int(score), dedup.get(str(role), 0))
    ranked = sorted(dedup.items(), key=lambda item: item[1], reverse=True)[:4]
    if len(ranked) == 1:
        ranked.append((tr(language, "label.unknown"), max(0, 100 - ranked[0][1])))
    if len(ranked) < 2:
        ranked = [(tr(language, "fallback.workflow_compute"), 60), (tr(language, "label.unknown"), 40)]
    return _renormalize_percent(ranked)


def _infer_primary_role(node: Any, language: str) -> str:
    kind = str(getattr(node, "kind", "")).lower()
    code = str(getattr(node, "code", ""))
    if "loop" in kind:
        return "Iteration" if language == "en" else "迭代"
    if kind in {"if", "condition"}:
        return tr(language, "fallback.workflow_validation")
    if "return" in code or kind == "exit":
        return "Output" if language == "en" else "输出"
    if "raise" in code:
        return "ExceptionHandling" if language == "en" else "异常处理"
    if getattr(node, "effects", []):
        return "SideEffect" if language == "en" else "副作用"
    return tr(language, "fallback.workflow_compute")


def _renormalize_percent(items: list[tuple[str, int]]) -> list[list[Any]]:
    total = sum(max(0, int(score)) for _, score in items)
    if total <= 0:
        even = int(round(100 / max(1, len(items))))
        result = [[role, even] for role, _ in items]
    else:
        result = [[role, int(round(max(0, score) * 100 / total))] for role, score in items]
    drift = 100 - sum(item[1] for item in result)
    if result:
        result[0][1] = max(0, min(100, result[0][1] + drift))
    return result


def _normalize_uncertainty(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"L", "M", "H"}:
        return text
    if text in {"LOW"}:
        return "L"
    if text in {"MEDIUM"}:
        return "M"
    if text in {"HIGH"}:
        return "H"
    return "M"


def _clip_percent(value: Any, default: int) -> int:
    try:
        num = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(0, min(100, num))
