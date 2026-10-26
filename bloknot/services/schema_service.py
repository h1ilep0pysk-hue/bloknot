"""Схема ↔ JSON, версия формата, миграции (SPEC_STORAGE п. 3, 5, 7). Без Qt."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ..core.models import Edge, Node, SchemaGraph, new_id
from ..core.node_types import default_params, get_spec, is_known
from ..core.validation import clean_schema

SCHEMA_VERSION = 2
MAX_REPR = 1000


@dataclass
class LoadResult:
    schema: SchemaGraph
    runtime: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    reset: bool = False          # файл не прочитан, схема сброшена


def empty_schema_json() -> str:
    return json.dumps({"version": SCHEMA_VERSION, "nodes": [], "edges": []}, ensure_ascii=False)


def serialize(schema: SchemaGraph, runtime: dict[str, Any] | None = None) -> str:
    data = {
        "version": SCHEMA_VERSION,
        "nodes": [
            {"id": n.id, "type": n.type, "title": n.title,
             "x": float(n.x), "y": float(n.y), "params": n.params}
            for n in schema.nodes
        ],
        "edges": [
            {"id": e.id, "from_node": e.from_node, "from_port": e.from_port,
             "to_node": e.to_node, "to_port": e.to_port}
            for e in schema.edges
        ],
        "runtime": runtime or {},
    }
    return json.dumps(data, ensure_ascii=False, default=str)


def _float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _int(v: Any) -> int | None:
    try:
        if isinstance(v, bool):
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def deserialize(text: str) -> LoadResult:
    """Битый JSON / отсутствует ключ → пустая схема и reset=True; приложение не падает."""
    try:
        data = json.loads(text)
        if not isinstance(data, dict) or not isinstance(data.get("nodes"), list) \
                or not isinstance(data.get("edges"), list):
            raise ValueError("структура схемы")

        version = _int(data.get("version")) or 1
        runtime = data.get("runtime") if isinstance(data.get("runtime"), dict) else {}
        if version < 2:                                   # миграция 1 → 2
            runtime = {}

        nodes: list[Node] = []
        for raw in data["nodes"]:
            if not isinstance(raw, dict):
                continue
            type_ = str(raw.get("type") or "unknown")
            spec = get_spec(type_)
            params = raw.get("params") if isinstance(raw.get("params"), dict) else {}
            if is_known(type_):                           # недостающие параметры — из default
                merged = default_params(spec)
                merged.update(params)
                params = merged
            title = raw.get("title")
            nodes.append(Node(
                id=str(raw.get("id") or new_id()),
                type=type_,
                title=title if isinstance(title, str) and title else spec.title,
                x=_float(raw.get("x")), y=_float(raw.get("y")),
                params=params,
            ))

        edges: list[Edge] = []
        for raw in data["edges"]:
            if not isinstance(raw, dict):
                continue
            fp, tp = _int(raw.get("from_port")), _int(raw.get("to_port"))
            if fp is None or tp is None or not raw.get("from_node") or not raw.get("to_node"):
                continue
            edges.append(Edge(id=str(raw.get("id") or new_id()),
                              from_node=str(raw["from_node"]), from_port=fp,
                              to_node=str(raw["to_node"]), to_port=tp))

        schema = SchemaGraph(nodes, edges)
        warnings = clean_schema(schema)
        return LoadResult(schema, runtime, warnings)
    except (ValueError, TypeError, KeyError, AttributeError):
        return LoadResult(SchemaGraph(), {}, [], reset=True)
