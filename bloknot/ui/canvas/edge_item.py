"""Пунктирная связь-Безье (SPEC_UI п. 5.5)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject, QGraphicsSceneHoverEvent, QGraphicsSceneMouseEvent

from .. import theme
from ..widgets import make_anim

HIT_WIDTH = 8
END_HIT = 12


def bezier(p0: QPointF, p1: QPointF) -> QPainterPath:
    """Кубическая Безье с горизонтальными контрольными точками, смещение max(40, 0.5*dx)."""
    off = max(40.0, 0.5 * abs(p1.x() - p0.x()))
    path = QPainterPath(p0)
    path.cubicTo(QPointF(p0.x() + off, p0.y()), QPointF(p1.x() - off, p1.y()), p1)
    return path


class EdgeItem(QGraphicsObject):
    """Связь модели (edge_id задан) или временная связь при перетаскивании (edge_id=None)."""

    def __init__(self, edge_id: str | None, scene) -> None:
        super().__init__()
        self.edge_id = edge_id
        self._gscene = scene
        self.src_port = None          # PortItem выхода
        self.dst_port = None          # PortItem входа
        self._p0 = QPointF()
        self._p1 = QPointF()
        self._path = QPainterPath()
        self._hover_t = 0.0
        self._hover_anim = make_anim(self, self._set_hover)
        self.setZValue(-1)
        if edge_id is not None:
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            self.setAcceptHoverEvents(True)

    def bind(self, src_port, dst_port) -> None:
        self.src_port, self.dst_port = src_port, dst_port
        self.update_path()

    def update_path(self) -> None:
        if self.src_port is not None:
            self._p0 = self.src_port.scene_center()
        if self.dst_port is not None:
            self._p1 = self.dst_port.scene_center()
        self.set_points(self._p0, self._p1)

    def set_points(self, p0: QPointF, p1: QPointF) -> None:
        self.prepareGeometryChange()
        self._p0, self._p1 = p0, p1
        self._path = bezier(p0, p1)
        self.update()

    @property
    def end_point(self) -> QPointF:
        return self._p1

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self._path.boundingRect().adjusted(-HIT_WIDTH, -HIT_WIDTH, HIT_WIDTH, HIT_WIDTH)

    def shape(self) -> QPainterPath:
        s = QPainterPathStroker()
        s.setWidth(HIT_WIDTH)
        return s.createStroke(self._path)

    def _set_hover(self, v: float) -> None:
        self._hover_t = v
        self.update()

    def hoverEnterEvent(self, e: QGraphicsSceneHoverEvent) -> None:  # noqa: N802
        self._fade(1.0)

    def hoverLeaveEvent(self, e: QGraphicsSceneHoverEvent) -> None:  # noqa: N802
        self._fade(0.0)

    def _fade(self, to: float) -> None:
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_t)
        self._hover_anim.setEndValue(to)
        self._hover_anim.start()

    def paint(self, p: QPainter, *_a) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.edge_id is not None and self.isSelected():
            color, width = theme.qcolor(theme.ACCENT), 2.0
        elif self.edge_id is not None:
            color = theme.mix(theme.BORDER, theme.TEXT_SECONDARY, self._hover_t)
            width = 1.4 + 0.2 * self._hover_t
        else:
            color, width = theme.qcolor(theme.BORDER), 1.4
        pen = QPen(color, width)
        pen.setDashPattern([4, 4])
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(self._path)

    # Нажатие на конец связи у входа — отделить её и тянуть заново (standard n8n UX)
    def mousePressEvent(self, e: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        if (self.edge_id is not None and e.button() == Qt.MouseButton.LeftButton
                and (e.scenePos() - self._p1).manhattanLength() <= END_HIT * 1.5):
            if self._gscene.begin_reconnect(self, e.scenePos()):
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        if self._gscene.dragging:
            self._gscene.update_link(e.scenePos())
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        if self._gscene.dragging and e.button() == Qt.MouseButton.LeftButton:
            self._gscene.finish_link(e.scenePos())
        else:
            super().mouseReleaseEvent(e)
