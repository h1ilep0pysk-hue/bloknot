"""QGraphicsScene: узлы, связи, создание/переподключение связей, выделение (SPEC_UI п. 5.3–5.5)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Signal
from PySide6.QtWidgets import QGraphicsScene

from ...core.models import Edge, Node, Project
from ...services.flow_service import FlowService
from ...services.project_service import ConnectResult, ProjectService
from .edge_item import EdgeItem
from .node_item import NODE_W, PORT_HIT, SNAP, NodeItem, PortItem

SCENE_EXTENT = 10000
SNAP_R = 24.0          # радиус «прилипания» к порту в координатах сцены


@dataclass
class _Drag:
    mode: str                       # "new" | "reconnect"
    src_port: PortItem
    temp: EdgeItem
    edge_item: EdgeItem | None = None
    hover: PortItem | None = None


class GraphScene(QGraphicsScene):
    node_activated = Signal(str)          # двойной клик по телу узла → открыть панель параметров
    param_edited = Signal(str, str)       # (node_id, key): параметр изменён inline-виджетом
    values_changed = Signal(list)         # ids узлов, чьё runtime-состояние обновилось
    message = Signal(str)                 # короткое сообщение в статус-бар

    def __init__(self, service: ProjectService, flow: FlowService) -> None:
        super().__init__()
        self.service, self.flow = service, flow
        self.live = True
        self.node_items: dict[str, NodeItem] = {}
        self.edge_items: dict[str, EdgeItem] = {}
        self._drag: _Drag | None = None
        self.setSceneRect(-SCENE_EXTENT, -SCENE_EXTENT, 2 * SCENE_EXTENT, 2 * SCENE_EXTENT)
        flow.register_listener(self._on_values)

    # ───────────── загрузка ─────────────
    def load(self, project: Project | None) -> None:
        self.cancel_drag()
        self.clear()
        self.node_items, self.edge_items = {}, {}
        if project is None:
            return
        for node in project.schema.nodes:
            self._add_node_item(node)
        for edge in project.schema.edges:
            self._add_edge_item(edge)
        self.update_port_states()

    def content_center(self) -> QPointF:
        if not self.node_items:
            return QPointF(0, 0)
        rect = QRectF()
        for it in self.node_items.values():
            rect = rect.united(it.sceneBoundingRect())
        return rect.center()

    # ───────────── узлы ─────────────
    def _add_node_item(self, node: Node) -> NodeItem:
        item = NodeItem(node, self)
        self.addItem(item)
        self.node_items[node.id] = item
        return item

    def add_node_at(self, type_: str, pos: QPointF) -> NodeItem | None:
        x, y = round(pos.x() / SNAP) * SNAP, round(pos.y() / SNAP) * SNAP
        node = self.service.add_node(type_, x, y)
        if node is None:
            return None
        item = self._add_node_item(node)
        self.clearSelection()
        item.setSelected(True)
        return item

    def delete_selected(self) -> None:
        sel = self.selectedItems()
        node_ids = [i.node.id for i in sel if isinstance(i, NodeItem)]
        edge_ids = [i.edge_id for i in sel if isinstance(i, EdgeItem) and i.edge_id]
        for eid in edge_ids:
            if self.service.remove_edge(eid):
                self._drop_edge_item(eid)
        if node_ids:
            for eid in self.service.remove_nodes(node_ids):
                self._drop_edge_item(eid)
            for nid in node_ids:
                item = self.node_items.pop(nid, None)
                if item is not None:
                    self.removeItem(item)
        self.update_port_states()

    def duplicate_selected(self) -> None:
        new_items = []
        for item in [i for i in self.selectedItems() if isinstance(i, NodeItem)]:
            node = self.service.duplicate_node(item.node.id)
            if node is not None:
                new_items.append(self._add_node_item(node))
        if new_items:
            self.clearSelection()
            for it in new_items:
                it.setSelected(True)

    def commit_positions(self) -> None:
        pos = {nid: (it.x(), it.y()) for nid, it in self.node_items.items()
               if (it.node.x, it.node.y) != (it.x(), it.y())}
        if pos:
            self.service.move_nodes(pos)

    def sync_param(self, node_id: str, key: str) -> None:
        """Панель изменила параметр — обновить inline-виджет узла (если есть)."""
        item = self.node_items.get(node_id)
        if item is not None:
            item.sync_param(key)

    def chain_of(self, node_id: str) -> set[str]:
        """Все узлы, связанные с node_id связями (в обе стороны) — «цепочка»."""
        if self.service.current is None:
            return {node_id}
        adj: dict[str, set[str]] = {}
        for e in self.service.current.schema.edges:
            adj.setdefault(e.from_node, set()).add(e.to_node)
            adj.setdefault(e.to_node, set()).add(e.from_node)
        seen, stack = {node_id}, [node_id]
        while stack:
            for m in adj.get(stack.pop(), ()):
                if m not in seen:
                    seen.add(m)
                    stack.append(m)
        return seen

    # ───────────── связи ─────────────
    def _add_edge_item(self, edge: Edge) -> EdgeItem | None:
        src, dst = self.node_items.get(edge.from_node), self.node_items.get(edge.to_node)
        if src is None or dst is None or edge.from_port >= len(src.out_ports) \
                or edge.to_port >= len(dst.in_ports):
            return None
        item = EdgeItem(edge.id, self)
        item.bind(src.out_ports[edge.from_port], dst.in_ports[edge.to_port])
        self.addItem(item)
        self.edge_items[edge.id] = item
        return item

    def _drop_edge_item(self, edge_id: str) -> None:
        item = self.edge_items.pop(edge_id, None)
        if item is not None:
            self.removeItem(item)

    def update_edges_of(self, node_id: str) -> None:
        for e in self.edge_items.values():
            if e.src_port.node_item.node.id == node_id or e.dst_port.node_item.node.id == node_id:
                e.update_path()

    def update_port_states(self) -> None:
        used_out: set[tuple[str, int]] = set()
        used_in: set[tuple[str, int]] = set()
        if self.service.current:
            for e in self.service.current.schema.edges:
                used_out.add((e.from_node, e.from_port))
                used_in.add((e.to_node, e.to_port))
        for nid, it in self.node_items.items():
            for p in it.out_ports:
                p.set_connected((nid, p.index) in used_out)
            for p in it.in_ports:
                p.set_connected((nid, p.index) in used_in)

    def edge_into(self, node_id: str, port_index: int) -> EdgeItem | None:
        for e in self.edge_items.values():
            if e.dst_port.node_item.node.id == node_id and e.dst_port.index == port_index:
                return e
        return None

    def _apply(self, res: ConnectResult) -> bool:
        for eid in res.removed_edge_ids:
            self._drop_edge_item(eid)
        if res.edge is not None:
            self._add_edge_item(res.edge)
        self.update_port_states()
        if res.error:
            self.message.emit(res.error[:1].upper() + res.error[1:])
            return False
        return True

    # ── перетаскивание связи ──
    @property
    def dragging(self) -> bool:
        return self._drag is not None

    def _start_drag(self, mode: str, port: PortItem, pos: QPointF) -> None:
        self.cancel_drag()
        temp = EdgeItem(None, self)
        self.addItem(temp)
        self._drag = _Drag(mode, port, temp)
        self._draw_temp(pos)

    def begin_link(self, port: PortItem, pos: QPointF) -> None:
        """Связь от ВЫХОДА к входу."""
        self._start_drag("new", port, pos)

    def begin_link_from_input(self, port: PortItem, pos: QPointF) -> None:
        """Связь от свободного ВХОДА к выходу (обратное направление)."""
        self._start_drag("reverse", port, pos)

    def begin_reconnect(self, edge_item: EdgeItem, pos: QPointF) -> bool:
        if edge_item.edge_id is None or edge_item.src_port is None:
            return False
        self.cancel_drag()
        temp = EdgeItem(None, self)
        self.addItem(temp)
        edge_item.setVisible(False)
        self._drag = _Drag("reconnect", edge_item.src_port, temp, edge_item)
        self._draw_temp(pos)
        return True

    def begin_reconnect_at(self, node_id: str, port_index: int, pos: QPointF) -> bool:
        edge = self.edge_into(node_id, port_index)
        return edge is not None and self.begin_reconnect(edge, pos)

    # ── «прилипание»: поиск порта-цели ──
    def _resolve_target(self, pos: QPointF, want_output: bool,
                        exclude_node: str | None = None) -> PortItem | None:
        """Цель отпускания. 1) порт нужного направления в радиусе SNAP_R от курсора;
        2) иначе — узел под курсором: его свободный порт, ближайший по вертикали."""
        best, best_d = None, SNAP_R
        for nid, item in self.node_items.items():
            if nid == exclude_node:
                continue
            for p in (item.out_ports if want_output else item.in_ports):
                c = p.scene_center()
                d = math.hypot(c.x() - pos.x(), c.y() - pos.y())
                if d <= best_d:
                    best, best_d = p, d
        if best is not None:
            return best
        for nid, item in self.node_items.items():
            if nid == exclude_node or not item.sceneBoundingRect().contains(pos):
                continue
            ports = item.out_ports if want_output else item.in_ports
            if not ports:
                continue
            return min(ports, key=lambda p: (p.connected if not want_output else False,
                                             abs(p.scene_center().y() - pos.y())))
        return None

    def port_at(self, pos: QPointF) -> PortItem | None:
        """Совместимость: вход под курсором (для переподключения)."""
        return self._resolve_target(pos, want_output=False)

    def _draw_temp(self, pos: QPointF) -> None:
        d = self._drag
        if d is None:
            return
        anchor = d.src_port.scene_center()
        if d.mode == "reverse":                  # кривая всегда рисуется от выхода к входу
            d.temp.set_points(pos, anchor)
        else:
            d.temp.set_points(anchor, pos)

    def update_link(self, pos: QPointF) -> None:
        d = self._drag
        if d is None:
            return
        self._draw_temp(pos)
        exclude = d.src_port.node_item.node.id if d.mode in ("new", "reverse") else None
        cand = self._resolve_target(pos, want_output=(d.mode == "reverse"), exclude_node=exclude)
        if cand is not d.hover:
            if d.hover is not None:
                d.hover.set_highlighted(False)
            if cand is not None:
                cand.set_highlighted(True)
            d.hover = cand

    def finish_link(self, pos: QPointF) -> None:
        d = self._drag
        if d is None:
            return
        exclude = d.src_port.node_item.node.id if d.mode in ("new", "reverse") else None
        cand = self._resolve_target(pos, want_output=(d.mode == "reverse"), exclude_node=exclude)
        self._end_drag()
        if d.mode == "new":
            if cand is not None:
                self._apply(self.service.add_edge(d.src_port.node_item.node.id, d.src_port.index,
                                                  cand.node_item.node.id, cand.index))
            return
        if d.mode == "reverse":
            if cand is not None:
                self._apply(self.service.add_edge(cand.node_item.node.id, cand.index,
                                                  d.src_port.node_item.node.id, d.src_port.index))
            return
        # reconnect: переносим вход существующей связи
        eid = d.edge_item.edge_id
        if cand is not None:
            res = self.service.reconnect_edge(eid, cand.node_item.node.id, cand.index)
            if not self._apply(res):
                d.edge_item.setVisible(True)             # отказ: связь остаётся как была
        else:
            if self.service.remove_edge(eid):
                self._drop_edge_item(eid)
            self.update_port_states()

    def cancel_drag(self) -> None:
        d = self._drag
        if d is None:
            return
        self._end_drag()
        if d.edge_item is not None:
            d.edge_item.setVisible(True)

    def _end_drag(self) -> None:
        d, self._drag = self._drag, None
        if d is None:
            return
        if d.hover is not None:
            d.hover.set_highlighted(False)
        self.removeItem(d.temp)

    # ───────────── значения ─────────────
    def _on_values(self, ids: list[str]) -> None:
        for nid in ids:
            it = self.node_items.get(nid)
            if it is not None:
                it.refresh()
        self.values_changed.emit(list(ids))

    def set_live(self, on: bool) -> None:
        self.live = on
        for it in self.node_items.values():
            it.refresh()

    def refresh_all(self) -> None:
        for it in self.node_items.values():
            it.refresh()

    # ───────────── зум из inline-виджетов ─────────────
    def wheel_zoom(self, delta_y: int, global_pos) -> None:
        views = self.views()
        if views:
            views[0].wheel_zoom(delta_y, global_pos)
