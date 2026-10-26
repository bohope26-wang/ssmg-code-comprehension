import json
from typing import Any

from app.services.localization import normalize_language, prompt_language_instruction, tr


def build_partition_prompt(
    source_code: str,
    function_name: str,
    bb_nodes: list[dict[str, Any]],
    cfg_edges: list[dict[str, Any]],
    max_modules: int,
    language: str = "en",
) -> str:
    language = normalize_language(language)
    blocks_json = json.dumps(bb_nodes, ensure_ascii=False, indent=2)
    edges_json = json.dumps(cfg_edges, ensure_ascii=False, indent=2)
    module_name = tr(language, "fallback.workflow_validation")
    module_desc = tr(language, "fallback.module_desc", label=module_name.lower())
    output_schema = {
        "function_summary": tr(language, "fallback.function_summary"),
        "modules": [
            {
                "module_id": "M1",
                "name": module_name,
                "description": module_desc,
                "bb_ids": ["BB0", "BB1"],
            }
        ],
    }

    return f"""You are partitioning one Python function into semantic modules at the basic-block level.
{prompt_language_instruction(language)}

Task definition:
- Partition the function into modules using the provided basic blocks.
- Each basic block must belong to exactly one module.
- `{max_modules}` is only an upper bound. Do not try to create exactly {max_modules} modules.
- Choose the module count according to the function's actual complexity and semantic stages.
- As a rough guide: short functions usually need 4-6 modules, medium functions usually need 6-8 modules, and long functions usually need 7-9 modules.
- Module counts do not need to be equal across functions.
- Prioritize complete semantic phases and explainable boundaries over matching any target module count.
- Group BBs by semantic responsibility and their role in the function's control/data flow.
- Use the full function source, BB metadata, and CFG edges together; do not rely only on lexical similarity.
- Prefer modules that a human reader could use to understand the function's end-to-end workflow.
- Avoid over-fragmenting adjacent BBs that work together toward the same responsibility.
- Split adjacent BBs when they clearly represent different semantic stages, such as validation, computation, side effects, error handling, cleanup, or return.
- Module names should be short but meaningful responsibility labels.
- Do not invent nonexistent BB ids.
- Output must be strict JSON only, with no Markdown code fences.

Function name:
{function_name}

Function source code:
{source_code}

Basic blocks:
{blocks_json}

CFG edges:
{edges_json}

Required output JSON shape:
{json.dumps(output_schema, ensure_ascii=False, indent=2)}

Output rules:
- Every BB id from the basic block list must appear exactly once.
- Keep module_id unique.
- Keep descriptions concise, but make them describe the module's actual responsibility.
- The function_summary should briefly describe the function's end-to-end workflow.
- Do not include BB ids in a module unless the code in those BBs supports the module name and description.
- Natural-language values in `function_summary`, `modules[*].name`, and `modules[*].description` must follow the language requirement above.
"""


def one_shot_schema_hint(language: str = "en") -> dict[str, Any]:
    language = normalize_language(language)
    return {
        "function_summary": tr(language, "fallback.function_summary"),
        "modules": [
            {
                "module_id": "M1",
                "name": tr(language, "fallback.workflow_validation"),
                "description": tr(language, "fallback.module_desc", label=tr(language, "fallback.workflow_validation").lower()),
                "bb_ids": ["BB0", "BB1"],
            }
        ],
    }
