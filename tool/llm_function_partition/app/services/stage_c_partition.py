from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.llm_json import LLMJsonCallResult, call_llm_json
from app.services.localization import prompt_language_instruction, tr
from app.services.schemas import CFGPayload, RuntimeConfig, StageABOutput, StageCOutput


logger = logging.getLogger(__name__)


def run_stage_c_partition(
    cfg: CFGPayload,
    stage_ab: StageABOutput,
    runtime_config: RuntimeConfig,
) -> tuple[StageCOutput, dict[str, Any]]:
    logger.info("StageC start function=%s bb_count=%s", runtime_config.function_name, len(cfg.bb_nodes))
    prompt = _build_stage_c_prompt(cfg=cfg, stage_ab=stage_ab, runtime_config=runtime_config)
    schema_hint = {
        "stage": "stage_c_candidate_partition_v1",
        "function_name": runtime_config.function_name,
        "candidates": [
            {
                "id": "C1",
                "mods": [
                    {
                        "id": "T1",
                        "label": tr(runtime_config.language, "fallback.workflow_validation"),
                        "desc": tr(runtime_config.language, "fallback.module_desc", label=tr(runtime_config.language, "fallback.workflow_validation").lower()),
                        "more_specific_desc": tr(
                            runtime_config.language,
                            "fallback.module_specific",
                            label=tr(runtime_config.language, "fallback.workflow_validation").lower(),
                        ),
                        "bbs": ["BB1"],
                        "evi": ["BB1"],
                        "conf": 80,
                    }
                ],
            }
        ],
    }
    llm_result: LLMJsonCallResult | None = None
    stage_error = ""
    try:
        llm_result = call_llm_json(
            prompt=prompt,
            model=runtime_config.model_for_stage("c"),
            temperature=runtime_config.temperature,
            stage_name="stage_c_partition",
            schema_hint=schema_hint,
            llm_config=runtime_config.llm,
            max_format_retries=runtime_config.llm.max_format_retries,
            language=runtime_config.language,
        )
        parsed = llm_result.parsed_json
    except RuntimeError as exc:
        logger.warning("StageC failed; fallback to deterministic candidate error=%s", exc)
        parsed = {}
        stage_error = str(exc)

    repaired = _repair_stage_c_payload(parsed=parsed, cfg=cfg, stage_ab=stage_ab, runtime_config=runtime_config)
    stage_c = StageCOutput.model_validate(repaired)
    debug = {
        "prompt": prompt,
        "language": runtime_config.language,
        "raw_response_text": llm_result.raw_response_text if llm_result else "",
        "parsed_response": llm_result.parsed_json if llm_result else {},
        "attempts": llm_result.attempts if llm_result else 0,
        "error": stage_error,
    }
    logger.info("StageC done function=%s candidates=%s", runtime_config.function_name, len(stage_c.candidates))
    return stage_c, debug


def _build_stage_c_prompt(cfg: CFGPayload, stage_ab: StageABOutput, runtime_config: RuntimeConfig) -> str:
    cfg_payload = cfg.model_dump(mode="json", by_alias=True)

    stage_ab_payload = stage_ab.model_dump(mode="json", by_alias=True)
    ablation_note = (
        "You may output 2-3 candidates."
        if runtime_config.multi_candidates_debug
        else "Output exactly 1 main candidate."
    )
    validation_label = tr(runtime_config.language, "fallback.workflow_validation")
    validation_desc = tr(runtime_config.language, "fallback.module_desc", label=validation_label.lower())
    validation_specific = tr(runtime_config.language, "fallback.module_specific", label=validation_label.lower())
    return f"""
You are Stage C: candidate module partition synthesis with short and detailed semantic descriptions.
{prompt_language_instruction(runtime_config.language)}

Your task is to propose candidate semantic module partitions for one function.

Stage C is NOT the final decision layer.
Its role in the pipeline is:
- Stage AB gives weak global hypotheses and BB-level semantic skeleton
- Stage C groups BBs into candidate semantic modules
- Stage D will later verify, repair, and make the final partition decision

Therefore:
- You are generating candidate partitions, not final truth
- You must propose modules that are semantically coherent and useful for human understanding
- You must NOT output final truth claims or risk conclusions
- You must NOT output repair decisions
- You must NOT assume your result will be accepted unchanged by Stage D

Rules:
- Input contract is JSON-only: CFG.json + stage_ab_global_bb.json
- {ablation_note}
- `max_modules` is {runtime_config.max_modules}, and it is only an upper bound. Do not try to create exactly that many modules.
- Keep `desc` to one sentence only
- Keep `more_specific_desc` under 150 words
- Keep output compact
- One JSON object only
- No markdown fences
- No extra text outside JSON

==================================================
[Stage role in the system]

This stage is responsible for:
1. grouping BBs into candidate semantic modules
2. assigning each candidate module a short semantic label
3. assigning each candidate module a one-sentence short description
4. assigning each candidate module a more specific flow description
5. selecting evidence BBs that best support the module meaning

This stage is NOT responsible for:
- final partition truth
- final module IDs
- final risk judgment
- final repair or correction
- final structural legality check

==================================================
[What you should optimize for]

When proposing candidate modules, optimize for:
- semantic cohesion inside each module
- compact and interpretable end-to-end flow
- usefulness for human understanding
- avoiding overly fragmented modules
- avoiding merging clearly different responsibilities into one module

Prefer modules that match how a human would explain the function to another engineer.

==================================================
[Boundary decision rules]

Prefer setting module boundaries where:
1. The semantic goal changes, such as input normalization to core computation, or candidate construction to result aggregation.
2. The main operation target changes, such as database collections to fields, provider to room, or ledger to bank.
3. The key intermediate artifact changes, such as `allowed_len`, `uri`, `array`, `decision`, `schedule`, `alerts`, or `partition`.
4. The flow enters mutually exclusive main branches or independent processing paths, such as sparse/dense, zip/tar, streamed/non-streamed, or receive/reserve/ship.
5. A group of validations shares one error meaning or jointly serves the same later stage; keep that validation group together as one module.
6. A single-line `return` usually belongs to the previous module. Only entry short-circuit returns or branch short-circuit returns may become their own module.

Do NOT split modules merely because of:
1. multi-line function calls, dictionary literals, list comprehensions, or string concatenation
2. several consecutive `if` checks under the same local goal
3. comments or docstrings
4. small temporary assignments that only serve the next step
5. small updates inside one loop body that all serve the same accumulated state

==================================================
[Granularity constraints]

- `max_modules` is an upper bound, not a target.
- Short functions(below 50 lines) usually need 4-6 modules.
- Medium functions(50 lines to 110 lines) usually need 6-8 modules.
- Long functions(more than 110 lines) usually need 7-9 modules.
- Module counts do not need to be equal across functions.
- Prefer complete semantic phases and explainable boundaries over matching any fixed module count.
- If the function is too small to support the usual range, use fewer meaningful modules.

==================================================
[Meaning of top-level fields]

- `stage`
  Fixed string:
  `"stage_c_candidate_partition_v1"`

- `function_name`
  Copy the provided function name exactly.

- `candidates`
  A list of candidate partition proposals.
  Each candidate is one possible way to divide the function into semantic modules.
  These are candidate proposals only, not final truth.

==================================================
[Meaning of fields inside `candidates`]

1. `id`
Meaning:
- Candidate partition ID.
- Example: `"C1"`, `"C2"`

How to fill:
- Use short candidate IDs starting from `C1`.

2. `mods`
Meaning:
- The list of temporary modules in this candidate partition.
- Each module is a semantic group of BBs.

How to fill:
- Every BB from the function should appear in exactly one module of the candidate.
- Do not omit BBs.
- Do not duplicate BB assignment inside the same candidate.
- Keep the number of modules reasonable, compact, and no greater than `max_modules`.

==================================================
[Meaning of fields inside each module in `mods`]

1. `id`
Meaning:
- Temporary module ID inside the candidate.
- Example: `"T1"`, `"T2"`

How to fill:
- Use temporary IDs only.
- These are not final IDs.
- Stage D may later rename them to `M1`, `M2`, etc.

2. `label`
Meaning:
- A short semantic label for the module.
- This should summarize the module's main responsibility.

How to fill:
- Keep it short and reusable.
- Prefer labels like:
  "Setup", "Validation", "Compute", "Transform", "Persist", "Notify", "ErrorHandling", "Cleanup"
- The label should describe the module as a whole, not just one BB.

Do NOT:
- Do not use long sentences
- Do not use vague labels like "Logic", "Process", "Handle"
- Do not simply copy one BB's `cr`

3. `desc`
Meaning:
- A one-sentence short natural language explanation of what the module does.
- This is meant to help human readers understand the module quickly.

How to fill:
- Exactly one short sentence
- Concrete and functional
- Describe the module's main responsibility in human terms

Do NOT:
- Do not write multiple sentences
- Do not write long rationale
- Do not describe the entire function
- Do not mention future repair or uncertainty here

4. `bbs`
Meaning:
- The BB IDs assigned to this module.

How to fill:
- Include all BBs belonging to this module
- Preserve a reasonable flow-oriented grouping
- BBs should form a semantically coherent module

Do NOT:
- Do not omit BBs
- Do not repeat BBs across modules in the same candidate

5. `evi`
Meaning:
- Evidence BB IDs for this module
- These are the most representative BBs that best support why the module has this label and description

How to fill:
- Choose 1 to 3 BBs
- Prefer BBs that contain strong semantic evidence
- Prefer BBs with clear calls / effects / control roles / responsibility cues
- Use BBs that a human reviewer could inspect to verify the module meaning

Do NOT:
- Do not include all BBs unless the module is tiny
- Do not choose weak or ambiguous BBs if clearer evidence exists

6. `conf`
Meaning:
- Confidence score for the module definition inside this candidate
- This reflects how coherent and well-supported the module grouping appears

How to fill:
- Integer from 0 to 100
- Higher when:
  - module responsibility is clear
  - evidence BBs strongly support the label
  - grouping is cohesive
- Lower when:
  - module is mixed or transitional
  - evidence is weak
  - grouping is uncertain

7. `more_specific_desc`
Meaning:
- A more specific natural-language explanation of how the module behaves internally.
- This field is for module detail panels, not module graph labels.
- This field should describe more specific ,just like how do the key variables change,what do the key variables mean.
- This field should describe more specific ,just like what is the input and output of this module and more description that can help programmers understand this piece of code.

How to fill:
- Keep it under 400 words
- Describe the local code flow inside the module in a reviewer-friendly way
- Mention important checks, transformations, side effects, or exits when they matter

Do NOT:
- Do not repeat the full-function story
- Do not discuss repair, risk, or confidence
- Do not produce bullet lists
- Do not exceed 400 words

==================================================
[How to use Stage AB]

Use `stage_ab_global_bb.json` as semantic prior, not as binding truth.

- Use `global.function_summary_candidates` as broad context
- Use `global.workflow_hypotheses` as coarse process hints
- Use `global.coarse_boundary_hints` as weak hints for possible module transitions
- Use `global.uncertain_regions` to know where interpretation is less stable
- Use `bb[*].cr` to understand control-flow role
- Use `bb[*].rc` to understand semantic responsibility candidates
- Use `bb[*].u` to detect ambiguity or transitional BBs

Important:
- Do not blindly follow Stage AB
- If local grouping evidence suggests a better partition, prefer the better partition
- Stage AB is prior knowledge, not final authority

==================================================
[Key distinctions you must respect]

- Stage AB gives local semantic skeleton
- Stage C must convert that skeleton into module-level candidate grouping

This means:
- You are not labeling BBs individually
- You are grouping BBs into modules
- Your output is module-level, not BB-level

Also:
- `label` is module-level semantic responsibility
- `desc` is a short human-readable explanation
- `evi` is evidence for the module claim
- `bbs` is the actual module content

These are different and should not be confused.

==================================================
[Partition quality guidelines]

A good candidate partition should:
- cover all BBs exactly once
- avoid too many tiny modules
- avoid mixing clearly different responsibilities
- reflect a plausible end-to-end business/process flow
- remain interpretable to human readers

Choose the module count that best preserves complete semantic stages and explainable boundaries.

==================================================
[Output style constraints]

- Output one JSON object only
- No extra keys
- No comments
- No markdown
- Keep text concise
- Use integers for all confidence values
- Natural-language values in `mods[*].label`, `mods[*].desc`, and `mods[*].more_specific_desc` must follow the language requirement above.

==================================================
Function name:
{runtime_config.function_name}

CFG.json:
{json.dumps(cfg_payload, ensure_ascii=False, indent=2)}

stage_ab_global_bb.json:
{json.dumps(stage_ab_payload, ensure_ascii=False, indent=2)}

Output schema:
{{
  "stage": "stage_c_candidate_partition_v1",
  "function_name": "{runtime_config.function_name}",
  "candidates": [
    {{
      "id": "C1",
      "mods": [
        {{
          "id": "T1",
          "label": {json.dumps(validation_label, ensure_ascii=False)},
          "desc": {json.dumps(validation_desc, ensure_ascii=False)},
          "more_specific_desc": {json.dumps(validation_specific, ensure_ascii=False)},
          "bbs": ["BB1", "BB2"],
          "evi": ["BB2"],
          "conf": 81
        }}
      ]
    }}
  ]
}}
""" 


def _repair_stage_c_payload(
    *,
    parsed: dict[str, Any],
    cfg: CFGPayload,
    stage_ab: StageABOutput,
    runtime_config: RuntimeConfig,
) -> dict[str, Any]:
    valid_ids = [node.id for node in cfg.bb_nodes]
    valid_set = set(valid_ids)
    max_candidates = min(runtime_config.max_candidates, 3) if runtime_config.multi_candidates_debug else 1

    raw_candidates = parsed.get("candidates", []) if isinstance(parsed, dict) else []
    candidates: list[dict[str, Any]] = []
    if isinstance(raw_candidates, list):
        for idx, item in enumerate(raw_candidates[:max_candidates], start=1):
            if not isinstance(item, dict):
                continue
            candidate_id = str(item.get("id", f"C{idx}")).strip() or f"C{idx}"
            raw_mods = item.get("mods", [])
            mods = _repair_modules(raw_mods, valid_set, runtime_config.language)
            if not mods:
                continue
            candidates.append({"id": candidate_id, "mods": mods})

    if not candidates:
        candidates = [
            {
                "id": "C1",
                "mods": _fallback_modules_from_stage_ab(cfg, stage_ab, runtime_config.max_modules, runtime_config.language),
            }
        ]

    return {
        "stage": "stage_c_candidate_partition_v1",
        "function_name": runtime_config.function_name,
        "candidates": candidates,
    }


def _repair_modules(raw_mods: Any, valid_ids: set[str], language: str) -> list[dict[str, Any]]:
    if not isinstance(raw_mods, list):
        return []
    mods: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_mods, start=1):
        if not isinstance(item, dict):
            continue
        module_id = str(item.get("id", f"T{idx}")).strip() or f"T{idx}"
        label = _short_label(item.get("label"), fallback=f"{tr(language, 'label.module')}{idx}")
        desc = _one_sentence(item.get("desc"), fallback=tr(language, "fallback.module_desc", label=label.lower()))
        more_specific_desc = _specific_description(
            item.get("more_specific_desc"),
            fallback=tr(language, "fallback.module_specific", label=label.lower()),
        )
        bbs_raw = item.get("bbs", [])
        evi_raw = item.get("evi", [])
        bbs = _unique_ordered([str(bb).strip() for bb in bbs_raw if str(bb).strip() in valid_ids]) if isinstance(bbs_raw, list) else []
        if not bbs:
            continue
        evi = _unique_ordered([str(bb).strip() for bb in evi_raw if str(bb).strip() in bbs]) if isinstance(evi_raw, list) else []
        if not evi:
            evi = bbs[: min(2, len(bbs))]
        mods.append(
            {
                "id": module_id,
                "label": label,
                "desc": desc,
                "more_specific_desc": more_specific_desc,
                "bbs": bbs,
                "evi": evi,
                "conf": _clip_percent(item.get("conf"), default=60),
            }
        )

    # De-duplicate module IDs if needed.
    seen: set[str] = set()
    for idx, module in enumerate(mods, start=1):
        mid = module["id"]
        if mid in seen:
            module["id"] = f"T{idx}"
        seen.add(module["id"])
    return mods


def _fallback_modules_from_stage_ab(cfg: CFGPayload, stage_ab: StageABOutput, max_modules: int, language: str) -> list[dict[str, Any]]:
    role_by_bb = {item.id: _top_role(item.rc) for item in stage_ab.bb}
    ordered = sorted([node.id for node in cfg.bb_nodes], key=_bb_sort_key)
    if not ordered:
        label = tr(language, "label.module")
        return [
            {
                "id": "T1",
                "label": label,
                "desc": tr(language, "fallback.recovered_module"),
                "bbs": [],
                "evi": [],
                "conf": 45,
            }
        ]

    clusters: list[list[str]] = []
    current: list[str] = []
    current_role = ""
    for bb in ordered:
        role = role_by_bb.get(bb, "Compute")
        if not current:
            current = [bb]
            current_role = role
            continue
        if role != current_role and len(clusters) + 1 < max(2, max_modules):
            clusters.append(current)
            current = [bb]
            current_role = role
        else:
            current.append(bb)
    if current:
        clusters.append(current)

    modules = []
    for idx, cluster in enumerate(clusters, start=1):
        role = _role_label(_top_role_from_cluster(cluster, role_by_bb), language)
        modules.append(
            {
                "id": f"T{idx}",
                "label": role,
                "desc": _one_sentence(
                    tr(language, "fallback.module_desc", label=role.lower()),
                    fallback=tr(language, "fallback.module_desc", label=tr(language, "label.module").lower()),
                ),
                "more_specific_desc": _specific_description(
                    tr(language, "fallback.groups_role", role=role.lower()),
                    fallback=tr(language, "fallback.groups_region"),
                ),
                "bbs": cluster,
                "evi": cluster[: min(2, len(cluster))],
                "conf": 55,
            }
        )
    return modules


def _top_role(rc: list[list[Any]]) -> str:
    if not isinstance(rc, list) or not rc:
        return "Compute"
    ranked = sorted(rc, key=lambda item: _safe_int(item[1] if isinstance(item, list) and len(item) > 1 else 0), reverse=True)
    top = ranked[0]
    if isinstance(top, list) and top:
        return str(top[0]).strip() or "Compute"
    return "Compute"


def _top_role_from_cluster(cluster: list[str], role_by_bb: dict[str, str]) -> str:
    counts: dict[str, int] = {}
    for bb in cluster:
        role = role_by_bb.get(bb, "Compute")
        counts[role] = counts.get(role, 0) + 1
    if not counts:
        return "Compute"
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)[0][0]


def _role_label(role: str, language: str) -> str:
    text = (role or tr(language, "label.module")).strip().replace("_", " ")
    if not text:
        return tr(language, "label.module")
    return text[0].upper() + text[1:]


def _short_label(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    text = re.sub(r"\s+", " ", text)
    return text[:40]


def _one_sentence(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    text = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+", text)
    sentence = parts[0].strip() if parts else text
    if sentence and sentence[-1] not in ".!?":
        sentence += "."
    return sentence[:180]


def _specific_description(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    text = re.sub(r"\s+", " ", text)
    words = text.split()
    if len(words) > 150:
        text = " ".join(words[:150])
    if text and text[-1] not in ".!?":
        text += "."
    return text


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


def _clip_percent(value: Any, default: int) -> int:
    try:
        num = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(0, min(100, num))


def _bb_sort_key(bb_id: str) -> int:
    if bb_id.startswith("BB") and bb_id[2:].isdigit():
        return int(bb_id[2:])
    return 10**9
