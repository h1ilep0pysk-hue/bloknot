"""Редактирование проекта из UI: CRUD проектов и операции над графом. Без Qt."""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Any, Callable

from ..core.models import Edge, Node, Project, SchemaGraph, new_id, now_iso
from ..core.node_types import default_params, get_spec
from ..core.validation import can_connect
from ..storage.project_repository import ProjectRepository
from . import schema_service
from .flow_service import FlowService

log = logging.getLogger("bloknot.project")
IDEA_LIMIT = 280
DEFAULT_NAME = "Untitled"


@dataclass
class ProjectSummary:
    id: str
    name: str
    idea_summary: str


@dataclass
class ConnectResult:
    edge: Edge | None
    removed_edge_ids: list[str]
    error: str | None = None


def _noop(*_a: Any, **_k: Any) -> None:
    return None


class ProjectService:
    def __init__(self, repo: ProjectRepository, flow: FlowService) -> None:
        self.repo = repo
        self.flow = flow
        self.current: Project | None = None
        self._dirty = False
        # Колбэки в UI (таймеры debounce держит UI — SPEC_FLOW п. 4)
        self.on_dirty: Callable[[], None] = _noop              # перезапустить таймер записи 500 мс
        self.on_eval: Callable[[], None] = _noop               # перезапустить таймер пересчёта 200 мс
        self.on_message: Callable[[str, int], None] = _noop    # (текст, мс) в статус-бар
        self.on_saved: Callable[[], None] = _noop

    # ───────────── проекты ─────────────
    def list_projects(self) -> list[ProjectSummary]:
        return [ProjectSummary(r["id"], r["name"], r["idea_summary"]) for r in self.repo.get_all()]

    def create_project(self, name: str = DEFAULT_NAME) -> Project:
        self.flush()
        pid, ts = new_id(), now_iso()
        self.repo.create(pid, name.strip() or DEFAULT_NAME, "", "",
                         schema_service.empty_schema_json(), ts)
        project = self.open_project(pid)
        assert project is not None
        return project

    def open_project(self, project_id: str) -> Project | None:
        self.flush()
        row = self.repo.get(project_id)
        if row is None:
            return None
        loaded = schema_service.deserialize(row["schema_json"])
        self.current = Project(row["id"], row["name"], row["idea_summary"], row["description"],
                               loaded.schema, row["created_at"], row["updated_at"])
        self._dirty = False
        self.flow.init_runtime(loaded.schema, loaded.runtime)
        if loaded.reset:
            self.on_message("Схема не прочитана и была сброшена", 4000)
        elif loaded.warnings:
            self.on_message("Схема исправлена при загрузке", 4000)
        self.flow.invalidate_all()
        self.on_eval()
        return self.current

    def delete_project(self, project_id: str) -> None:
        if self.current and self.current.id == project_id:
            self.current = None
            self._dirty = False
            self.flow.set_schema(SchemaGraph())
        self.repo.delete(project_id)

    def update_text(self, name: str | None = None, idea: str | None = None,
                    description: str | None = None) -> None:
        p = self.current
        if p is None:
            return
        if name is not None:
            p.name = name
        if idea is not None:
            p.idea_summary = idea
        if description is not None:
            p.description = description
        self._mark_dirty()

    # ───────────── запись ─────────────
    @property
    def dirty(self) -> bool:
        return self._dirty

    def _mark_dirty(self) -> None:
        self._dirty = True
        self.on_dirty()

    def flush(self, force: bool = False) -> bool:
        p = self.current
        if p is None or not (self._dirty or force):
            return True
        p.name = p.name.strip() or DEFAULT_NAME
        p.idea_summary = p.idea_summary[:IDEA_LIMIT]
        try:
            row = self.repo.update(
                p.id, name=p.name, idea_summary=p.idea_summary, description=p.description,
                schema_json=schema_service.serialize(p.schema, self.flow.export_repr()))
        except Exception:  # noqa: BLE001 — диск/БД: приложение живёт, повтор на следующем debounce
            log.exception("не удалось сохранить проект")
            self.on_message("Не удалось сохранить", 4000)
            return False
        p.updated_at = row["updated_at"]
        self._dirty = False
        self.on_saved()
        return True

    # ───────────── граф ─────────────
    def _schema(self) -> SchemaGraph | None:
        return self.current.schema if self.current else None

    def node(self, node_id: str) -> Node | None:
        s = self._schema()
        return next((n for n in s.nodes if n.id == node_id), None) if s else None

    def add_node(self, type_: str, x: float, y: float) -> Node | None:
        s = self._schema()
        if s is None:
            return None
        spec = get_spec(type_)
        node = Node(new_id(), type_, spec.title, float(x), float(y), default_params(spec))
        s.nodes.append(node)
        self.flow.invalidate(node.id)
        self._mark_dirty()
        self.on_eval()
        return node

    def duplicate_node(self, node_id: str) -> Node | None:
        src, s = self.node(node_id), self._schema()
        if src is None or s is None:
            return None
        node = Node(new_id(), src.type, src.title, src.x + 30, src.y + 30, copy.deepcopy(src.params))
        s.nodes.append(node)
        self.flow.invalidate(node.id)
        self._mark_dirty()
        self.on_eval()
        return node

    def remove_nodes(self, node_ids: list[str]) -> list[str]:
        """Удаляет узлы и их связи; возвращает id удалённых связей."""
        s = self._schema()
        if s is None or not node_ids:
            return []
        gone = set(node_ids)
        removed = [e for e in s.edges if e.from_node in gone or e.to_node in gone]
        receivers = [e.to_node for e in removed if e.from_node in gone and e.to_node not in gone]
        s.edges = [e for e in s.edges if e not in removed]
        s.nodes = [n for n in s.nodes if n.id not in gone]
        for nid in gone:
            self.flow.forget(nid)
        self.flow.on_edges_changed(receivers)       # их входы станут None
        self._mark_dirty()
        self.on_eval()
        return [e.id for e in removed]

    def add_edge(self, from_node: str, from_port: int, to_node: str, to_port: int) -> ConnectResult:
        s = self._schema()
        if s is None:
            return ConnectResult(None, [], "нет открытого проекта")
        reason = can_connect(s, from_node, from_port, to_node, to_port)
        if reason:
            return ConnectResult(None, [], reason)
        old = [e for e in s.edges if e.to_node == to_node and e.to_port == to_port]   # один вход — одна связь
        s.edges = [e for e in s.edges if e not in old]
        edge = Edge(new_id(), from_node, from_port, to_node, to_port)
        s.edges.append(edge)
        self.flow.on_edges_changed([to_node])
        self._mark_dirty()
        self.on_eval()
        return ConnectResult(edge, [e.id for e in old])

    def remove_edge(self, edge_id: str) -> bool:
        s = self._schema()
        edge = next((e for e in s.edges if e.id == edge_id), None) if s else None
        if edge is None:
            return False
        s.edges = [e for e in s.edges if e.id != edge_id]
        self.flow.on_edges_changed([edge.to_node, edge.from_node])
        self._mark_dirty()
        self.on_eval()
        return True

    def reconnect_edge(self, edge_id: str, to_node: str, to_port: int) -> ConnectResult:
        """Переносит вход существующей связи; источник остаётся прежним."""
        s = self._schema()
        old = next((e for e in s.edges if e.id == edge_id), None) if s else None
        if old is None:
            return ConnectResult(None, [], "связь не найдена")
        reason = can_connect(s, old.from_node, old.from_port, to_node, to_port)
        if reason:
            return ConnectResult(None, [], reason)
        self.remove_edge(edge_id)
        res = self.add_edge(old.from_node, old.from_port, to_node, to_port)
        res.removed_edge_ids.append(edge_id)
        return res

    def set_param(self, node_id: str, key: str, value: Any) -> None:
        node = self.node(node_id)
        if node is None or node.params.get(key) == value and key in node.params:
            return
        node.params[key] = value
        self.flow.invalidate(node_id)
        self._mark_dirty()
        self.on_eval()

    def set_title(self, node_id: str, title: str) -> None:
        node = self.node(node_id)
        if node is None or node.title == title:
            return
        node.title = title
        self._mark_dirty()                          # переименование не влияет на данные — без пересчёта

    def move_nodes(self, positions: dict[str, tuple[float, float]]) -> None:
        changed = False
        for nid, (x, y) in positions.items():
            node = self.node(nid)
            if node and (node.x != x or node.y != y):
                node.x, node.y = float(x), float(y)
                changed = True
        if changed:
            self._mark_dirty()
