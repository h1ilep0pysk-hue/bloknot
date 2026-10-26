"""Правила целостности графа (SPEC_CORE п. 10, SPEC_FLOW п. 8). Без Qt."""
from __future__ import annotations

from collections import deque
from typing import Iterable

from .models import Edge, SchemaGraph
from .node_types import get_spec


def reachable(edges: Iterable[Edge], start: str, target: str) -> bool:
    """BFS по направлению связей: достижим ли target из start."""
    adj: dict[str, list[str]] = {}
    for e in edges:
        adj.setdefault(e.from_node, []).append(e.to_node)
    seen = {start}
    queue = deque([start])
    while queue:
        n = queue.popleft()
        if n == target:
            return True
        for m in adj.get(n, ()):
            if m not in seen:
                seen.add(m)
                queue.append(m)
    return False


def can_connect(schema: SchemaGraph, from_node: str, from_port: int,
                to_node: str, to_port: int) -> str | None:
    """None — можно; иначе причина отказа (текст для статус-бара)."""
    if from_node == to_node:
        return "нельзя соединить узел с самим собой"
    nodes = {n.id: n for n in schema.nodes}
    src, dst = nodes.get(from_node), nodes.get(to_node)
    if src is None or dst is None:
        return "узел не найден"
    if not (0 <= from_port < len(get_spec(src.type).outputs)):
        return "у узла нет такого выхода"
    if not (0 <= to_port < len(get_spec(dst.type).inputs)):
        return "у узла нет такого входа"
    if reachable(schema.edges, to_node, from_node):
        return "цикл в схеме"
    return None


def topo_sort(node_ids: Iterable[str], edges: Iterable[Edge]) -> tuple[list[str], list[str]]:
    """Алгоритм Кана на подграфе. Возвращает (порядок, узлы цикла/зависшие за ним)."""
    ids = list(node_ids)
    idset = set(ids)
    indeg = {i: 0 for i in ids}
    adj: dict[str, list[str]] = {i: [] for i in ids}
    for e in edges:
        if e.from_node in idset and e.to_node in idset:
            adj[e.from_node].append(e.to_node)
            indeg[e.to_node] += 1
    queue = deque(i for i in ids if indeg[i] == 0)
    order: list[str] = []
    while queue:
        n = queue.popleft()
        order.append(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    done = set(order)
    return order, [i for i in ids if i not in done]


def clean_schema(schema: SchemaGraph) -> list[str]:
    """Чистка при загрузке (SPEC_STORAGE п. 7). Возвращает список предупреждений."""
    warnings: list[str] = []

    seen: set[str] = set()
    nodes = []
    for n in schema.nodes:
        if n.id in seen:
            warnings.append("повторяющийся id узла отброшен")
            continue
        seen.add(n.id)
        nodes.append(n)
    schema.nodes = nodes

    by_id = {n.id: n for n in nodes}
    seen_edges: set[str] = set()
    used_inputs: set[tuple[str, int]] = set()
    edges = []
    for e in schema.edges:
        if e.id in seen_edges:
            warnings.append("повторяющийся id связи отброшен")
            continue
        seen_edges.add(e.id)
        src, dst = by_id.get(e.from_node), by_id.get(e.to_node)
        if (src is None or dst is None or e.from_node == e.to_node
                or not (0 <= e.from_port < len(get_spec(src.type).outputs))
                or not (0 <= e.to_port < len(get_spec(dst.type).inputs))):
            warnings.append("связь с несуществующим узлом или портом удалена")
            continue
        key = (e.to_node, e.to_port)
        if key in used_inputs:                       # один вход — одна связь
            warnings.append("лишняя связь на занятый вход удалена")
            continue
        used_inputs.add(key)
        edges.append(e)
    schema.edges = edges
    return warnings
