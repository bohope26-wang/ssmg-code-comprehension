from __future__ import annotations

import ast
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

from app.services.localization import normalize_language, prompt_language_instruction, tr
from app.services.schemas import LLMConfig


load_dotenv()
logger = logging.getLogger(__name__)


@dataclass
class LLMJsonCallResult:
    raw_response_text: str
    parsed_json: dict[str, Any]
    attempts: int


def call_llm_json(
    prompt: str,
    model: str,
    temperature: float = 0.0,
    *,
    stage_name: str = "generic_stage",
    schema_hint: dict[str, Any] | None = None,
    llm_config: LLMConfig | None = None,
    max_format_retries: int | None = None,
    language: str = "en",
) -> LLMJsonCallResult:
    language = normalize_language(language)
    cfg = llm_config or LLMConfig()
    retries = cfg.max_format_retries if max_format_retries is None else max_format_retries
    retries = max(0, min(2, retries))

    api_key = os.getenv(cfg.api_key_env, "")
    if not api_key:
        raise RuntimeError(tr(language, "error.api_key_missing", env_name=cfg.api_key_env))

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(tr(language, "error.sdk_missing")) from exc

    client = OpenAI(
        api_key=api_key,
        base_url=cfg.base_url,
        timeout=float(cfg.timeout_sec),
    )

    raw_text = ""
    for attempt in range(retries + 1):
        user_prompt = prompt if attempt == 0 else _build_format_repair_prompt(raw_text, schema_hint, language)
        logger.info("LLM call stage=%s attempt=%s model=%s provider=%s", stage_name, attempt + 1, model, cfg.provider)
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Return strict JSON object only. No markdown fences. No extra commentary.\n"
                            f"{prompt_language_instruction(language)}"
                        ),
                    },
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as exc:
            raise RuntimeError(tr(language, "error.llm_request_failed", timeout=cfg.timeout_sec, error=exc)) from exc

        raw_text = _extract_content(response)
        try:
            parsed = _parse_json_text(raw_text, language)
            return LLMJsonCallResult(raw_response_text=raw_text, parsed_json=parsed, attempts=attempt + 1)
        except RuntimeError as exc:
            if attempt >= retries:
                raise RuntimeError(tr(language, "error.llm_invalid_after_retries", stage_name=stage_name, error=exc)) from exc
            logger.warning(
                "LLM invalid JSON stage=%s attempt=%s error=%s raw_preview=%r",
                stage_name,
                attempt + 1,
                exc,
                raw_text[:400],
            )

    raise RuntimeError(tr(language, "error.llm_failed_unexpected", stage_name=stage_name))


def _extract_content(response: Any) -> str:
    try:
        choice = response.choices[0]
        content = choice.message.content
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks: list[str] = []
            for part in content:
                text = ""
                if isinstance(part, dict):
                    text = str(part.get("text", "")).strip()
                else:
                    text = str(getattr(part, "text", "")).strip()
                if text:
                    chunks.append(text)
            return "\n".join(chunks).strip()
        return str(content or "").strip()
    except Exception:
        return ""


def _parse_json_text(raw_text: str, language: str = "en") -> dict[str, Any]:
    if not raw_text:
        raise RuntimeError(tr(language, "error.llm_empty"))

    candidate = raw_text.strip()
    parsed, parse_error = _try_parse_json_or_python_dict(candidate)
    if parsed is None:
        for recovered in _json_recovery_candidates(candidate):
            parsed, parse_error = _try_parse_json_or_python_dict(recovered)
            if parsed is not None:
                break
    if parsed is None:
        detail = f": {parse_error}" if parse_error else ""
        raise RuntimeError(tr(language, "error.llm_invalid_json", detail=detail))

    if not isinstance(parsed, dict):
        raise RuntimeError(tr(language, "error.llm_root_object"))
    return parsed


def _json_recovery_candidates(candidate: str) -> list[str]:
    candidates: list[str] = []
    text = candidate.strip()
    if text:
        candidates.append(text)

    fence_stripped = _strip_code_fence(text)
    if fence_stripped and fence_stripped != text:
        candidates.append(fence_stripped)

    first = fence_stripped.find("{")
    last = fence_stripped.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidates.append(fence_stripped[first : last + 1].strip())

    candidates.extend(_extract_brace_objects(fence_stripped))

    cleaned_candidates: list[str] = []
    for item in candidates:
        cleaned = _light_json_cleanup(item)
        cleaned_candidates.append(cleaned)

    seen: set[str] = set()
    unique: list[str] = []
    for item in candidates + cleaned_candidates:
        if not item or item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _light_json_cleanup(text: str) -> str:
    # Keep cleanup conservative: only fix common invalid JSON artifacts.
    output = text.strip()
    output = re.sub(r",(\s*[}\]])", r"\1", output)
    output = re.sub(r"\bNaN\b|\bInfinity\b|\b-Infinity\b", "null", output)
    return output


def _strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def _extract_brace_objects(text: str) -> list[str]:
    objects: list[str] = []
    start = -1
    depth = 0
    in_string = False
    escape = False
    for idx, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            if depth == 0:
                start = idx
            depth += 1
            continue
        if ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    objects.append(text[start : idx + 1].strip())
                    start = -1
    return objects


def _try_parse_json_or_python_dict(text: str) -> tuple[dict[str, Any] | None, str]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed, ""
        return None, "JSON root is not object"
    except json.JSONDecodeError as exc:
        last_error = str(exc)

    try:
        parsed_py = ast.literal_eval(text)
        if isinstance(parsed_py, dict):
            # Ensure it's JSON-serializable semantics.
            normalized = json.loads(json.dumps(parsed_py, ensure_ascii=False))
            if isinstance(normalized, dict):
                return normalized, ""
            return None, "literal_eval root is not object"
    except Exception:
        pass
    return None, last_error


def _build_format_repair_prompt(raw_text: str, schema_hint: dict[str, Any] | None, language: str) -> str:
    schema_text = json.dumps(schema_hint or {"type": "object"}, ensure_ascii=False, indent=2)
    return (
        "The previous output was not valid JSON.\n"
        "Rewrite it into one strict JSON object.\n"
        "No markdown code fences.\n"
        f"{prompt_language_instruction(language)}\n"
        f"Schema hint:\n{schema_text}\n\n"
        f"Previous output:\n{raw_text}"
    )
