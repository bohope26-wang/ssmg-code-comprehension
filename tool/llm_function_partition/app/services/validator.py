from collections import defaultdict
from typing import Any

from app.services.localization import tr


def normalize_and_validate_modules(
    raw_modules: list[dict[str, Any]],
    bb_nodes: list[dict[str, Any]],
    language: str = "en",
) -> dict[str, Any]:
    valid_bb_ids = {node["id"] for node in bb_nodes}
    assignments: dict[str, list[int]] = defaultdict(list)
    warnings: list[str] = []
    cleaned_modules: list[dict[str, Any]] = []

    for index, raw_module in enumerate(raw_modules, start=1):
        fallback_name = f"{tr(language, 'label.module')} {index}"
        name = str(raw_module.get("name", fallback_name)).strip() or fallback_name
        description = str(raw_module.get("description", "")).strip()
        bb_ids_value = raw_module.get("bb_ids", [])
        if not isinstance(bb_ids_value, list):
            warnings.append(tr(language, "warning.module_non_list", name=name))
            bb_ids_value = []

        kept_ids: list[str] = []
        for bb_id in bb_ids_value:
            if bb_id not in valid_bb_ids:
                warnings.append(tr(language, "warning.unknown_bb_dropped", bb_id=bb_id, name=name))
                continue
            kept_ids.append(bb_id)
            assignments[bb_id].append(index)

        cleaned_modules.append(
            {
                "name": name,
                "description": description,
                "bb_ids": kept_ids,
            }
        )

    duplicate_ids = {bb_id for bb_id, owners in assignments.items() if len(owners) > 1}
    if duplicate_ids:
        warnings.append(tr(language, "warning.duplicate_assignments", bb_ids=", ".join(sorted(duplicate_ids))))
        seen: set[str] = set()
        for module in cleaned_modules:
            unique_ids: list[str] = []
            for bb_id in module["bb_ids"]:
                if bb_id in seen:
                    continue
                seen.add(bb_id)
                unique_ids.append(bb_id)
            module["bb_ids"] = unique_ids

    assigned = {bb_id for module in cleaned_modules for bb_id in module["bb_ids"]}
    missing = sorted(valid_bb_ids - assigned)
    if missing:
        warnings.append(tr(language, "warning.unassigned_recovered", bb_ids=", ".join(missing)))
        cleaned_modules.append(
            {
                "name": tr(language, "label.recovered"),
                "description": tr(language, "fallback.auto_recovered"),
                "bb_ids": missing,
            }
        )

    final_modules = [module for module in cleaned_modules if module["bb_ids"]]
    if not final_modules:
        raise ValueError(tr(language, "error.no_valid_modules"))

    module_metadata: list[dict[str, Any]] = []
    partition: dict[str, str] = {}
    for index, module in enumerate(final_modules, start=1):
        module_id = f"M{index}"
        bb_ids = list(dict.fromkeys(module["bb_ids"]))
        module_metadata.append(
            {
                "module_id": module_id,
                "name": module["name"],
                "description": module["description"],
                "bb_ids": bb_ids,
            }
        )
        for bb_id in bb_ids:
            partition[bb_id] = module_id

    if set(partition) - valid_bb_ids:
        raise ValueError(tr(language, "error.partition_unknown"))
    if valid_bb_ids - set(partition):
        raise ValueError(tr(language, "error.partition_incomplete"))

    return {
        "partition": partition,
        "warnings": warnings,
        "module_metadata": module_metadata,
    }
