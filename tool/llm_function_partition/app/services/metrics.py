from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable

from app.services.schemas import CFGPayload


def module_components(cfg: CFGPayload, bb_ids: Iterable[str]) -> list[set[str]]:
    bb_set = set(bb_ids)
    if not bb_set:
        return []

    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in cfg.cfg_edges:
        if edge.from_ in bb_set and edge.to in bb_set:
            adjacency[edge.from_].add(edge.to)
            adjacency[edge.to].add(edge.from_)

    components: list[set[str]] = []
    seen: set[str] = set()
    for bb in bb_set:
        if bb in seen:
            continue
        queue: deque[str] = deque([bb])
        component: set[str] = set()
        seen.add(bb)
        while queue:
            cur = queue.popleft()
            component.add(cur)
            for nxt in adjacency.get(cur, set()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        components.append(component)
    return components


def disconnected_module_count(cfg: CFGPayload, partition: dict[str, str]) -> int:
    grouped: dict[str, list[str]] = defaultdict(list)
    for bb, module_id in partition.items():
        grouped[module_id].append(bb)

    count = 0
    for bb_ids in grouped.values():
        if len(module_components(cfg, bb_ids)) > 1:
            count += 1
    return count


def singleton_module_count(partition: dict[str, str]) -> int:
    grouped: dict[str, int] = defaultdict(int)
    for module_id in partition.values():
        grouped[module_id] += 1
    return sum(1 for size in grouped.values() if size == 1)
