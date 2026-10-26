from dataclasses import dataclass
from typing import Any

from app.services.localization import tr
from app.services.validator import normalize_and_validate_modules


@dataclass
class PartitionResult:
    partition: dict[str, str]
    warnings: list[str]
    function_summary: str
    module_metadata: list[dict[str, Any]]


def normalize_partition_result(
    parsed_response: dict[str, Any],
    bb_nodes: list[dict[str, Any]],
    language: str = "en",
) -> PartitionResult:
    function_summary = str(parsed_response.get("function_summary", "")).strip()
    raw_modules = parsed_response.get("modules")
    if not isinstance(raw_modules, list):
        raise ValueError(tr(language, "error.modules_missing"))

    normalized = normalize_and_validate_modules(raw_modules, bb_nodes, language=language)
    return PartitionResult(
        partition=normalized["partition"],
        warnings=normalized["warnings"],
        function_summary=function_summary,
        module_metadata=normalized["module_metadata"],
    )
