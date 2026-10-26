"""Доменные модели (SPEC_CORE п. 1–3). Без Qt."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def new_id() -> str:
    return uuid.uuid4().hex


def now_iso() -> str:
    """ISO 8601 UTC без микросекунд и без смещения: «2026-10-26T12:34:56»."""
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None).isoformat()


@dataclass
class Node:
    id: str
    type: str
    title: str
    x: float
    y: float
    params: dict = field(default_factory=dict)


@dataclass
class Edge:
    id: str
    from_node: str
    from_port: int
    to_node: str
    to_port: int


@dataclass
class SchemaGraph:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


@dataclass
class Project:
    id: str
    name: str
    idea_summary: str
    description: str
    schema: SchemaGraph
    created_at: str
    updated_at: str


@dataclass
class NodeRuntime:
    outputs: dict[str, Any] | None = None   # {"порт": значение} или None (не считался)
    error: str | None = None                # текст ошибки; None = нет ошибки
    dirty: bool = True                      # данные устарели
    display_value: Any | None = None        # для дисплей-узлов (result)
    restored: bool = False                  # значения — repr-строки из файла (SPEC_FLOW п. 10)
