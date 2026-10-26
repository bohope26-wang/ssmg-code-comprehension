from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.models import GenerateTasksRequest, GenerateTasksResponse, TaskQuizQuestion
from app.services.llm_json import LLMJsonCallResult, call_llm_json
from app.services.localization import normalize_language, prompt_language_instruction, tr
from app.services.schemas import LLMConfig


logger = logging.getLogger(__name__)


def generate_task_quiz(payload: GenerateTasksRequest) -> GenerateTasksResponse:
    language = normalize_language(payload.language)
    llm_config = LLMConfig.model_validate(payload.llm or {})
    prompt = _build_task_prompt(payload)
    schema_hint = {
        "function_name": payload.function_name,
        "questions": [
            {
                "id": "Q1",
                "type": "single_choice",
                "question": tr(language, "task.schema_question"),
                "options": [
                    {"id": "A", "text": tr(language, "task.schema_option_setup")},
                    {"id": "B", "text": tr(language, "task.schema_option_validation")},
                    {"id": "C", "text": tr(language, "task.schema_option_compute")},
                    {"id": "D", "text": tr(language, "task.schema_option_persist")},
                ],
                "answer": "B",
                "explanation": tr(language, "task.schema_explanation"),
                "evidence": {
                    "modules": ["M2"],
                    "bb_ids": ["BB3", "BB4"],
                    "line_spans": [[12, 16], [24, 28]],
                },
            }
        ],
    }

    llm_result: LLMJsonCallResult | None = None
    try:
        llm_result = call_llm_json(
            prompt=prompt,
            model=payload.model,
            temperature=payload.temperature,
            stage_name="generate_tasks",
            schema_hint=schema_hint,
            llm_config=llm_config,
            max_format_retries=llm_config.max_format_retries,
            language=language,
        )
        repaired = _repair_task_payload(llm_result.parsed_json, payload)
        return GenerateTasksResponse.model_validate(
            {
                "language": language,
                "function_name": payload.function_name,
                "generation_mode": "llm",
                "warning": None,
                "questions": repaired["questions"],
            }
        )
    except RuntimeError as exc:
        logger.warning("Task generation failed; using fallback function=%s error=%s", payload.function_name, exc)
        fallback_questions = _fallback_questions(payload)
        return GenerateTasksResponse(
            language=language,
            function_name=payload.function_name,
            generation_mode="fallback",
            warning=str(exc),
            questions=[TaskQuizQuestion.model_validate(item) for item in fallback_questions],
        )


def _build_task_prompt(payload: GenerateTasksRequest) -> str:
    language = normalize_language(payload.language)
    cfg_payload = payload.cfg
    module_graph_payload = payload.module_graph
    module_evidence_payload = payload.module_evidence or {}
    stage_outputs_payload = payload.stage_outputs or {}

    return f"""
You are generating task-oriented comprehension questions for one Python function analysis result.
{prompt_language_instruction(language)}

Goal:
- Help a reader verify whether they truly understand the current module partition result
- Questions must target the analyzed function and its current partition outcome
- Questions must be answerable from the provided artifacts

Output requirements:
- Return one JSON object only
- No markdown fences
- No extra commentary
- Generate exactly {payload.question_count} questions
- Use only `single_choice`
- Each question must include:
  - `question`
  - `options`
  - `answer`
  - `explanation`
  - `evidence`
- Evidence must point to modules, BB ids, and line spans when possible

Question design requirements:
- Focus on module responsibility, boundary understanding, main flow, side effects, return/exit behavior, or modification entry points
- Avoid generic Python syntax trivia
- Make distractors plausible but clearly separable using the given artifacts
- Prefer concise but concrete explanations
- Each explanation should explicitly connect back to the cited evidence
- Natural-language values in `question`, `options[*].text`, and `explanation` must follow the language requirement above.

JSON schema:
{{
  "function_name": "{payload.function_name}",
  "questions": [
    {{
      "id": "Q1",
      "type": "single_choice",
      "question": {json.dumps(tr(language, "task.schema_question"), ensure_ascii=False)},
      "options": [
        {{"id": "A", "text": {json.dumps(tr(language, "task.schema_option_setup"), ensure_ascii=False)}}},
        {{"id": "B", "text": {json.dumps(tr(language, "task.schema_option_validation"), ensure_ascii=False)}}},
        {{"id": "C", "text": {json.dumps(tr(language, "task.schema_option_compute"), ensure_ascii=False)}}},
        {{"id": "D", "text": {json.dumps(tr(language, "task.schema_option_persist"), ensure_ascii=False)}}}
      ],
      "answer": "B",
      "explanation": {json.dumps(tr(language, "task.schema_explanation"), ensure_ascii=False)},
      "evidence": {{
        "modules": ["M1"],
        "bb_ids": ["BB1", "BB2"],
        "line_spans": [[10, 12], [13, 16]]
      }}
    }}
  ]
}}

Artifacts:

CFG.json:
{json.dumps(cfg_payload, ensure_ascii=False, indent=2)}

partition.json:
{json.dumps(payload.partition, ensure_ascii=False, indent=2)}

module_graph.json:
{json.dumps(module_graph_payload, ensure_ascii=False, indent=2)}

cfg_by_module.json:
{json.dumps(payload.cfg_by_module, ensure_ascii=False, indent=2)}

module_evidence.json:
{json.dumps(module_evidence_payload, ensure_ascii=False, indent=2)}

stage_outputs.json:
{json.dumps(stage_outputs_payload, ensure_ascii=False, indent=2)}
"""


def _repair_task_payload(parsed: dict[str, Any], payload: GenerateTasksRequest) -> dict[str, Any]:
    valid_modules = {str(module.get("id", "")).strip() for module in payload.module_graph.get("modules", []) if module.get("id")}
    valid_bbs = {str(node.get("id", "")).strip() for node in payload.cfg.get("bb_nodes", []) if node.get("id")}
    line_lookup = {
        str(node.get("id", "")).strip(): [node.get("start_line"), node.get("end_line")]
        for node in payload.cfg.get("bb_nodes", [])
        if node.get("id")
    }

    questions: list[dict[str, Any]] = []
    raw_questions = parsed.get("questions", []) if isinstance(parsed, dict) else []
    if isinstance(raw_questions, list):
        for idx, raw in enumerate(raw_questions, start=1):
            if not isinstance(raw, dict):
                continue
            normalized = _repair_question(raw, idx, valid_modules, valid_bbs, line_lookup)
            if normalized:
                questions.append(normalized)

    if len(questions) < 3:
        fallback = _fallback_questions(payload)
        existing_ids = {item["id"] for item in questions}
        for item in fallback:
            if item["id"] in existing_ids:
                continue
            questions.append(item)
            if len(questions) >= max(3, payload.question_count):
                break

    questions = questions[: payload.question_count]
    return {"function_name": payload.function_name, "questions": questions}


def _repair_question(
    raw: dict[str, Any],
    index: int,
    valid_modules: set[str],
    valid_bbs: set[str],
    line_lookup: dict[str, list[int | None]],
) -> dict[str, Any] | None:
    question_text = _clean_text(raw.get("question"), fallback="")
    explanation = _clean_text(raw.get("explanation"), fallback="")
    if not question_text or not explanation:
        return None

    raw_options = raw.get("options", [])
    options: list[dict[str, str]] = []
    if isinstance(raw_options, list):
        for opt_idx, item in enumerate(raw_options[:5]):
            if not isinstance(item, dict):
                continue
            option_id = str(item.get("id", chr(65 + opt_idx))).strip().upper() or chr(65 + opt_idx)
            text = _clean_text(item.get("text"), fallback="")
            if not text:
                continue
            options.append({"id": option_id, "text": text})

    if len(options) < 2:
        return None

    answer = str(raw.get("answer", "")).strip().upper()
    valid_option_ids = {item["id"] for item in options}
    if answer not in valid_option_ids:
        answer = options[0]["id"]

    evidence_raw = raw.get("evidence", {}) if isinstance(raw.get("evidence"), dict) else {}
    modules = [item for item in _string_list(evidence_raw.get("modules")) if item in valid_modules]
    bb_ids = [item for item in _string_list(evidence_raw.get("bb_ids")) if item in valid_bbs]
    line_spans = _repair_line_spans(evidence_raw.get("line_spans"), bb_ids, line_lookup)

    return {
        "id": str(raw.get("id", f"Q{index}")).strip() or f"Q{index}",
        "type": "single_choice",
        "question": question_text,
        "options": options,
        "answer": answer,
        "explanation": explanation,
        "evidence": {
            "modules": modules,
            "bb_ids": bb_ids,
            "line_spans": line_spans,
        },
    }


def _repair_line_spans(value: Any, bb_ids: list[str], line_lookup: dict[str, list[int | None]]) -> list[list[int | None]]:
    spans: list[list[int | None]] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, list) and len(item) >= 2:
                spans.append([_maybe_int(item[0]), _maybe_int(item[1])])

    if spans:
        return spans

    fallback: list[list[int | None]] = []
    for bb_id in bb_ids:
        line_span = line_lookup.get(bb_id)
        if line_span:
            fallback.append([line_span[0], line_span[1]])
    return fallback


def _fallback_questions(payload: GenerateTasksRequest) -> list[dict[str, Any]]:
    language = normalize_language(payload.language)
    modules = list(payload.module_graph.get("modules", []))
    if not modules:
        return []

    bb_lookup = {str(node.get("id", "")): node for node in payload.cfg.get("bb_nodes", [])}
    evidence_lookup = {
        str(item.get("module_id", "")): item
        for item in (payload.module_evidence or {}).get("module_evidence", [])
        if item.get("module_id")
    }
    options = _module_options(modules)
    questions: list[dict[str, Any]] = []

    first_module = modules[0]
    first_module_id = str(first_module.get("id", "M1"))
    first_evidence = evidence_lookup.get(first_module_id, {})
    questions.append(
        _build_choice_question(
            qid="Q1",
            question=tr(
                language,
                "task.q1",
                description=first_module.get("description", tr(language, "task.q1_default")),
            ),
            correct_module=first_module,
            modules=modules,
            explanation=tr(language, "task.q1_explanation", module_id=first_module.get("id", "M1")),
            evidence=_evidence_for_module(first_module, first_evidence, bb_lookup),
            options=options,
        )
    )

    target_module = _module_with_max_evidence(evidence_lookup, modules)
    target_module_id = str(target_module.get("id", "M1"))
    target_evidence = evidence_lookup.get(target_module_id, {})
    bb_ids = target_evidence.get("evidence", [])
    bb_label = None
    if bb_ids:
        bb_label = bb_ids[0].get("bb_id")
    elif target_module.get("bb_ids"):
        bb_label = target_module["bb_ids"][0]
    questions.append(
        _build_choice_question(
            qid="Q2",
            question=tr(language, "task.q2", bb_label=bb_label or tr(language, "task.q2_default")),
            correct_module=target_module,
            modules=modules,
            explanation=tr(language, "task.q2_explanation", module_id=target_module_id),
            evidence=_evidence_for_module(target_module, target_evidence, bb_lookup),
            options=options,
        )
    )

    risky_module = _module_with_highest_risk(payload, modules)
    risky_module_id = str(risky_module.get("id", "M1"))
    risky_evidence = evidence_lookup.get(risky_module_id, {})
    questions.append(
        _build_choice_question(
            qid="Q3",
            question=tr(language, "task.q3"),
            correct_module=risky_module,
            modules=modules,
            explanation=tr(language, "task.q3_explanation", module_id=risky_module_id),
            evidence=_evidence_for_module(risky_module, risky_evidence, bb_lookup),
            options=options,
        )
    )

    if payload.question_count >= 4:
        transition_module = _next_module(modules, first_module_id) or first_module
        transition_id = str(transition_module.get("id", "M1"))
        transition_evidence = evidence_lookup.get(transition_id, {})
        questions.append(
            _build_choice_question(
                qid="Q4",
                question=tr(language, "task.q4", module_id=first_module.get("id", "M1")),
                correct_module=transition_module,
                modules=modules,
                explanation=tr(language, "task.q4_explanation", module_id=transition_id),
                evidence=_evidence_for_module(transition_module, transition_evidence, bb_lookup),
                options=options,
            )
        )

    if payload.question_count >= 5:
        last_module = modules[-1]
        last_evidence = evidence_lookup.get(str(last_module.get("id", "M1")), {})
        questions.append(
            _build_choice_question(
                qid="Q5",
                question=tr(language, "task.q5"),
                correct_module=last_module,
                modules=modules,
                explanation=tr(language, "task.q5_explanation", module_id=last_module.get("id", "M1")),
                evidence=_evidence_for_module(last_module, last_evidence, bb_lookup),
                options=options,
            )
        )

    return questions[: payload.question_count]


def _module_options(modules: list[dict[str, Any]]) -> list[dict[str, str]]:
    sample = modules[:4]
    if len(sample) < 2:
        sample = modules
    options: list[dict[str, str]] = []
    for idx, module in enumerate(sample[:4]):
        option_id = chr(65 + idx)
        options.append(
            {
                "id": option_id,
                "text": f"{module.get('id', option_id)}: {module.get('name', module.get('id', option_id))}",
            }
        )
    return options


def _build_choice_question(
    *,
    qid: str,
    question: str,
    correct_module: dict[str, Any],
    modules: list[dict[str, Any]],
    explanation: str,
    evidence: dict[str, Any],
    options: list[dict[str, str]],
) -> dict[str, Any]:
    module_id = str(correct_module.get("id", ""))
    fresh_options = [dict(item) for item in options]
    if not any(item["text"].startswith(f"{module_id}:") for item in fresh_options):
        fresh_options = _module_options(modules)
    answer = next((item["id"] for item in fresh_options if item["text"].startswith(f"{module_id}:")), fresh_options[0]["id"])
    return {
        "id": qid,
        "type": "single_choice",
        "question": question,
        "options": fresh_options,
        "answer": answer,
        "explanation": explanation,
        "evidence": evidence,
    }


def _evidence_for_module(module: dict[str, Any], evidence_bundle: dict[str, Any], bb_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    module_id = str(module.get("id", ""))
    evidence_items = evidence_bundle.get("evidence", []) if isinstance(evidence_bundle, dict) else []
    bb_ids: list[str] = []
    line_spans: list[list[int | None]] = []
    if isinstance(evidence_items, list):
        for item in evidence_items[:2]:
            if not isinstance(item, dict):
                continue
            bb_id = str(item.get("bb_id", "")).strip()
            if not bb_id:
                continue
            bb_ids.append(bb_id)
            line_span = item.get("line_span")
            if isinstance(line_span, list) and len(line_span) >= 2:
                line_spans.append([_maybe_int(line_span[0]), _maybe_int(line_span[1])])

    if not bb_ids:
        module_bb_ids = [str(bb).strip() for bb in module.get("bb_ids", []) if str(bb).strip()]
        bb_ids = module_bb_ids[:2]
        for bb_id in bb_ids:
            node = bb_lookup.get(bb_id, {})
            line_spans.append([node.get("start_line"), node.get("end_line")])

    return {"modules": [module_id], "bb_ids": bb_ids, "line_spans": line_spans}


def _module_with_max_evidence(evidence_lookup: dict[str, Any], modules: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(
        modules,
        key=lambda module: len((evidence_lookup.get(str(module.get("id", "")), {}) or {}).get("evidence", [])),
        reverse=True,
    )
    return ranked[0] if ranked else modules[0]


def _module_with_highest_risk(payload: GenerateTasksRequest, modules: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = (payload.stage_outputs.get("stage_d", {}) or {}).get("module_metadata", [])
    risk_rank = {"L": 0, "M": 1, "H": 2}
    risk_by_id = {
        str(item.get("module_id", "")).strip(): risk_rank.get(str(item.get("risk", "M")).strip(), 1)
        for item in metadata
        if isinstance(item, dict) and item.get("module_id")
    }
    ranked = sorted(modules, key=lambda module: risk_by_id.get(str(module.get("id", "")), -1), reverse=True)
    return ranked[0] if ranked else modules[0]


def _next_module(modules: list[dict[str, Any]], module_id: str) -> dict[str, Any] | None:
    for idx, module in enumerate(modules):
        if str(module.get("id", "")) != module_id:
            continue
        if idx + 1 < len(modules):
            return modules[idx + 1]
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _clean_text(value: Any, *, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    text = re.sub(r"\s+", " ", text)
    words = text.split()
    if len(words) > 90:
        text = " ".join(words[:90])
    return text


def _maybe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
