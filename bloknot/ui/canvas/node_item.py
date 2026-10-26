"""Визуальный узел: полоса состояния, порты, inline-виджеты, чип значения (SPEC_UI п. 5.4)."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsObject, QGraphicsProxyWidget,
                               QGraphicsSceneMouseEvent, QWidget)

from ...core.models import Node, NodeRuntime
from ...i18n import t
from ...core.node_types import NodeSpec, get_spec
from ...core.ports import to_plain
from .. import theme
from ..widgets import connect_change, make_anim, make_param_widget, write_value

NODE_W = 200
STRIPE_H = 3
HEADER_H = 24
PORT_ROW_H = 20
PORT_D = 9
PORT_HIT = 12
PAD = 12
CHIP_LINE_H = 14
CHIP_MAX_LINES = 5
CHIP_MAX_CHARS = 48
SNAP = 10
MIN_H = 56
RADIUS = 8


# ───────────── форматирование чипа (SPEC_UI п. 5.4) ─────────────
def _clip_lines(lines: list[str]) -> list[str]:
    lines = [ln if len(ln) <= CHIP_MAX_CHARS else ln[:CHIP_MAX_CHARS - 1] + "…" for ln in lines] or [""]
    if len(lines) > CHIP_MAX_LINES:
        lines = lines[:CHIP_MAX_LINES - 1] + ["…"]
    return lines


def format_lines(value: Any) -> list[str]:
    """Живое значение → строки чипа: списки/матрицы до 5 строк, строка ≤ 48 символов."""
    value = to_plain(value)
    if isinstance(value, (list, tuple)) and value and all(isinstance(r, (list, tuple)) for r in value):
        raw = [repr(list(r)) for r in value]
    else:
        raw = repr(value).splitlines() or [""]
    return _clip_lines(raw)


def text_lines(text: str) -> list[str]:
    return _clip_lines(str(text).splitlines() or [""])


class PortItem(QGraphicsItem):
    """Порт: кружок 9 px, хит-зона радиусом 12 px."""

    def __init__(self, node_item: "NodeItem", is_output: bool, index: int) -> None:
        super().__init__(node_item)
        self.node_item, self.is_output, self.index = node_item, is_output, index
        self.connected = False
        self.highlighted = False
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setZValue(2)

    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF(-PORT_HIT, -PORT_HIT, 2 * PORT_HIT, 2 * PORT_HIT)

    def shape(self) -> QPainterPath:
        p = QPainterPath()
        p.addEllipse(QPointF(0, 0), PORT_HIT, PORT_HIT)
        return p

    def scene_center(self) -> QPointF:
        return self.mapToScene(QPointF(0, 0))

    def set_connected(self, on: bool) -> None:
        if on != self.connected:
            self.connected = on
            self.update()

    def set_highlighted(self, on: bool) -> None:
        if on != self.highlighted:
            self.highlighted = on
            self.update()

    def paint(self, p: QPainter, *_a) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = PORT_D / 2
        if self.highlighted:
            fill, pen = theme.ACCENT, QPen(theme.qcolor(theme.TEXT_PRIMARY), 1.5)
        elif self.connected:
            fill, pen = theme.ACCENT, QPen(theme.qcolor(theme.ACCENT), 1)
        elif self.is_output:
            fill, pen = theme.TEXT_SECONDARY, QPen(theme.qcolor(theme.TEXT_SECONDARY), 1)
        else:
            fill, pen = theme.BG_ELEMENT, QPen(theme.qcolor(theme.BORDER), 1)
        p.setPen(pen)
        p.setBrush(theme.qcolor(fill))
        p.drawEllipse(QPointF(0, 0), r, r)

    # ── создание связей: нажатие на выход начинает связь, на занятый вход — переподключение ──
    def mousePressEvent(self, e: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        sc = self.scene()
        if e.button() == Qt.MouseButton.RightButton:
            sc.cancel_drag()
            e.accept()
            return
        if e.button() != Qt.MouseButton.LeftButton:
            e.ignore()
            return
        if self.is_output:
            sc.begin_link(self, e.scenePos())
            e.accept()
        elif self.connected:
            if sc.begin_reconnect_at(self.node_item.node.id, self.index, e.scenePos()):
                e.accept()
            else:
                e.ignore()
        else:                                   # свободный вход: связь в обратную сторону
            sc.begin_link_from_input(self, e.scenePos())
            e.accept()

    def mouseMoveEvent(self, e: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        self.scene().update_link(e.scenePos())

    def mouseReleaseEvent(self, e: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.scene().finish_link(e.scenePos())


class _InlineFilter(QObject):
    """eventFilter inline-виджетов: колесо → зум канвы; фокус → выделить узел (SPEC_UI п. 5.4)."""

    def __init__(self, node_item: "NodeItem") -> None:
        super().__init__(node_item)
        self._node_item = node_item

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:  # noqa: N802
        t = ev.type()
        if t == QEvent.Type.Wheel:
            self._node_item.scene().wheel_zoom(ev.angleDelta().y(), ev.globalPosition().toPoint())
            return True
        if t == QEvent.Type.FocusIn:
            self._node_item.select_only()
        return False


class NodeItem(QGraphicsObject):
    def __init__(self, node: Node, scene) -> None:
        super().__init__()
        self.node = node
        self.spec: NodeSpec = get_spec(node.type)
        self._gscene = scene
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setPos(node.x, node.y)
        self._moved = False
        self._h = float(MIN_H)

        # состояние отображения
        self._stripe = theme.BORDER_SUBTLE
        self._chip_lines: list[str] | None = None
        self._chip_color = theme.TEXT_MUTED
        self._chip_label: str | None = None
        self._is_receipt = self.spec.type == "result"
        self._flash_t = 1.0
        self._prev_text: str | None = None
        self._flash = make_anim(self, self._set_flash, 180)

        # порты
        self.in_ports = [PortItem(self, False, i) for i in range(len(self.spec.inputs))]
        self.out_ports = [PortItem(self, True, i) for i in range(len(self.spec.outputs))]

        # inline-виджеты (только исполняемые блоки; у проектных inline запрещён)
        self._filter = _InlineFilter(self)
        self._widgets: dict[str, QWidget] = {}
        self._proxies: list[tuple[QGraphicsProxyWidget, int]] = []
        if self.spec.runnable:
            for key, ps in self.spec.params.items():
                if not ps.inline:
                    continue
                w = make_param_widget(ps, node.params.get(key, ps.default), inline=True)
                connect_change(w, ps, lambda v, k=key: self._on_inline(k, v))
                for child in [w, *w.findChildren(QWidget)]:
                    child.installEventFilter(self._filter)
                proxy = QGraphicsProxyWidget(self)
                proxy.setWidget(w)
                proxy.setZValue(1)
                self._widgets[key] = w
                self._proxies.append((proxy, int(w.height())))

        self._relayout()
        self.refresh(first=True)

    # ───────────── геометрия ─────────────
    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF(-2, -2, NODE_W + 4, self._h + 4)

    def shape(self) -> QPainterPath:
        p = QPainterPath()
        p.addRoundedRect(QRectF(0, 0, NODE_W, self._h), RADIUS, RADIUS)
        return p

    @staticmethod
    def port_y(i: int) -> float:
        return STRIPE_H + HEADER_H + 14 + i * PORT_ROW_H

    def _chip_height(self) -> float:
        if self._chip_lines is None:
            return 0.0
        h = len(self._chip_lines) * CHIP_LINE_H
        return h + (8 if self._is_receipt else 0)

    def _relayout(self) -> None:
        rows = max(len(self.in_ports), len(self.out_ports))
        y = float(STRIPE_H + HEADER_H)
        if rows:
            y += 4 + rows * PORT_ROW_H
        for i, p in enumerate(self.in_ports):
            p.setPos(0, self.port_y(i))
        for i, p in enumerate(self.out_ports):
            p.setPos(NODE_W, self.port_y(i))
        if self._proxies:
            y += 4
            for proxy, h in self._proxies:
                proxy.setPos(PAD, y)
                y += h + 4
        if self._chip_lines is not None:
            y += 4
            if self._chip_label:
                y += 10
            self._chip_y = y
            y += self._chip_height()
        self._h = max(float(MIN_H), y + PAD)
        self.prepareGeometryChange()
        self.update()

    # ───────────── значения ─────────────
    def refresh(self, first: bool = False) -> None:
        st: NodeRuntime = self._gscene.flow.get_state(self.node.id)
        spec = self.spec

        # полоса состояния
        if st.error:
            self._stripe = theme.DANGER
        elif spec.type == "unknown" or not spec.runnable:
            self._stripe = theme.BORDER_SUBTLE
        else:
            self._stripe = theme.ACCENT

        lines: list[str] | None = None
        color = theme.TEXT_MUTED
        if spec.body_port is not None:
            lines, color = self._compute_chip(st)
        label = None
        if lines is not None:
            if st.restored:
                label = "восстановлено"
            elif st.dirty and not self._gscene.live:
                label = "устарело"

        text_key = None if lines is None else "\n".join(lines)
        if not first and text_key is not None and text_key != self._prev_text \
                and not st.restored and lines != ["—"]:
            self._flash.stop()
            self._flash_t = 0.0
            self._flash.setStartValue(0.0)
            self._flash.setEndValue(1.0)
            self._flash.start()
        self._prev_text = text_key

        relayout = (lines is None) != (self._chip_lines is None) \
            or (lines is not None and len(lines) != len(self._chip_lines or [])) \
            or (label is None) != (self._chip_label is None)
        self._chip_lines, self._chip_color, self._chip_label = lines, color, label
        if relayout:
            self._relayout()

        if st.error:
            self.setToolTip(st.error)
        elif spec.type == "unknown":
            self.setToolTip("этот тип узла не распознан")
        elif spec.opt_deps and not self._gscene.flow.has_numpy:
            self.setToolTip("установи numpy: pip install numpy")
        else:
            self.setToolTip("")
        self.update()

    def _compute_chip(self, st: NodeRuntime) -> tuple[list[str], str]:
        spec = self.spec
        dash = (["—"], theme.TEXT_MUTED)
        if st.error:
            return dash
        live_color = theme.ACCENT if (spec.runnable and not st.restored) else theme.TEXT_SECONDARY

        def one(v: Any) -> tuple[list[str], str]:
            if v is None:
                return dash
            if isinstance(v, str) and (st.restored or not spec.runnable):
                return text_lines(v), theme.TEXT_SECONDARY
            return format_lines(v), live_color

        if spec.body_port == "*":                       # ветка: «да: …» / «нет: …»
            outs = st.outputs or {}
            if not outs or all(v is None for v in outs.values()):
                return dash
            rows = []
            for p in spec.outputs:
                lns, _ = one(outs.get(p.name))
                rows.append(f"{p.caption}: {lns[0]}")
            return _clip_lines(rows), live_color
        if spec.fn is None:                             # дисплей-узел
            return one(st.display_value)
        if st.outputs is None:
            return dash
        return one(st.outputs.get(spec.body_port))

    def _set_flash(self, v: float) -> None:
        self._flash_t = v
        self.update()

    # ───────────── параметры ─────────────
    def _on_inline(self, key: str, value: Any) -> None:
        self._gscene.service.set_param(self.node.id, key, value)
        self._gscene.param_edited.emit(self.node.id, key)

    def sync_param(self, key: str) -> None:
        w = self._widgets.get(key)
        if w is not None:
            write_value(w, self.spec.params[key], self.node.params.get(key))

    def set_title(self, title: str) -> None:
        self.update()

    def select_only(self) -> None:
        if not self.isSelected():
            self._gscene.clearSelection()
            self.setSelected(True)

    # ───────────── рисование ─────────────
    def paint(self, p: QPainter, *_a) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(0, 0, NODE_W, self._h)
        path = QPainterPath()
        path.addRoundedRect(body, RADIUS, RADIUS)
        muted = self.spec.type == "unknown"

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor(theme.BG_PANEL))
        p.drawPath(path)

        p.save()                                         # полоса состояния 3 px, обрезанная по скруглению
        p.setClipPath(path)
        p.fillRect(QRectF(0, 0, NODE_W, STRIPE_H), theme.qcolor(self._stripe))
        p.restore()

        if self.isSelected():
            p.setPen(QPen(theme.qcolor(theme.ACCENT), 1.5))
        else:
            p.setPen(QPen(theme.qcolor(theme.BORDER), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(body.adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)

        # заголовок
        p.setFont(theme.ui_font(theme.PT_BASE, bold=True))
        p.setPen(theme.qcolor(theme.TEXT_MUTED if muted else theme.TEXT_PRIMARY))
        fm = p.fontMetrics()
        title = fm.elidedText(t(self.node.title), Qt.TextElideMode.ElideRight, NODE_W - 32)
        p.drawText(QRectF(16, STRIPE_H, NODE_W - 32, HEADER_H),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title)

        # подписи портов (если портов на стороне больше одного)
        p.setFont(theme.ui_font(theme.PT_PORT))
        p.setPen(theme.qcolor(theme.TEXT_MUTED))
        if len(self.spec.inputs) > 1:
            for i, port in enumerate(self.spec.inputs):
                p.drawText(QRectF(10, self.port_y(i) - 8, 80, 16),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, port.caption)
        if len(self.spec.outputs) > 1:
            for i, port in enumerate(self.spec.outputs):
                p.drawText(QRectF(NODE_W - 90, self.port_y(i) - 8, 80, 16),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, port.caption)

        # чип значения
        if self._chip_lines is not None:
            y = self._chip_y
            if self._chip_label:
                p.setFont(theme.ui_font(theme.PT_PORT))
                p.setPen(theme.qcolor(theme.TEXT_MUTED))
                p.drawText(QRectF(PAD, y - 12, NODE_W - 2 * PAD, 12),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._chip_label)
            color = theme.mix(theme.TEXT_PRIMARY, self._chip_color, self._flash_t)
            if self._is_receipt:                         # результат: чек во всю ширину узла
                box = QRectF(PAD, y, NODE_W - 2 * PAD, self._chip_height())
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(theme.qcolor(theme.BG_ELEMENT))
                p.drawRoundedRect(box, 6, 6)
                tx, ty = box.left() + 6, box.top() + 4
            else:
                tx, ty = PAD, y
            p.setFont(theme.mono_font(theme.PT_LABEL))
            p.setPen(color)
            for i, line in enumerate(self._chip_lines):
                p.drawText(QRectF(tx, ty + i * CHIP_LINE_H, NODE_W - 2 * PAD - 12, CHIP_LINE_H),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, line)

    # ───────────── события ─────────────
    def itemChange(self, change, value):  # noqa: N802
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene() is not None:
            return QPointF(round(value.x() / SNAP) * SNAP, round(value.y() / SNAP) * SNAP)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene() is not None:
            self._moved = True
            self._gscene.update_edges_of(self.node.id)
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()
        return super().itemChange(change, value)

    def mousePressEvent(self, e: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        self._moved = False
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        super().mouseReleaseEvent(e)
        if self._moved:                                  # в модель — один раз при отпускании
            self._moved = False
            self._gscene.commit_positions()

    def mouseDoubleClickEvent(self, e: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        self._gscene.node_activated.emit(self.node.id)
        e.accept()
