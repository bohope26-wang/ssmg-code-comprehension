from collections import defaultdict
from typing import Any


def build_module_graph(
    bb_nodes: list[dict[str, Any]],
    cfg_edges: list[dict[str, Any]],
    module_metadata: list[dict[str, Any]],
    partition: dict[str, str],
) -> dict[str, Any]:
    del bb_nodes
    seen: set[tuple[str, str]] = set()
    edges: list[dict[str, str]] = []
    for edge in cfg_edges:
        source_module = partition.get(edge["from"])
        target_module = partition.get(edge["to"])
        if not source_module or not target_module or source_module == target_module:
            continue
        key = (source_module, target_module)
        if key in seen:
            continue
        seen.add(key)
        edges.append({"from": source_module, "to": target_module})

    modules = [
        {
            "id": item["module_id"],
            "name": item.get("name", item["module_id"]),
            "description": item.get("description", ""),
            "bb_ids": item.get("bb_ids", []),
        }
        for item in module_metadata
    ]
    return {"modules": modules, "edges": edges}


def build_cfg_by_module(
    bb_nodes: list[dict[str, Any]],
    cfg_edges: list[dict[str, Any]],
    partition: dict[str, str],
) -> dict[str, Any]:
    node_lookup = {node["id"]: node for node in bb_nodes}
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"bb_nodes": [], "cfg_edges": []})

    for bb_id, module_id in partition.items():
        node = node_lookup.get(bb_id)
        if node:
            grouped[module_id]["bb_nodes"].append(node)

    for edge in cfg_edges:
        source_module = partition.get(edge["from"])
        target_module = partition.get(edge["to"])
        if source_module and source_module == target_module:
            grouped[source_module]["cfg_edges"].append(edge)

    return dict(grouped)

