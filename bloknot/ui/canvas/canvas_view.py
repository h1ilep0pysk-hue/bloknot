"""QGraphicsView: зум, пан, точечная сетка, drop из палитры (SPEC_UI п. 5.3)."""
from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPolygonF
from PySide6.QtWidgets import QGraphicsView

from .. import theme
from .node_item import NODE_W

MIME_NODE = "application/x-bloknot-node"
ZOOM_MIN, ZOOM_MAX = 0.25, 2.0
GRID_STEP = 20


class CanvasView(QGraphicsView):
    zoom_changed = Signal(float)

    def __init__(self, scene) -> None:
        super().__init__(scene)
        self._zoom = 1.0
        self._panning = False
        self._pan_last = QPoint()
        self._space = False
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self.setBackgroundBrush(theme.qcolor(theme.BG_WINDOW))
        self.centerOn(0, 0)

    # ───────────── сетка ─────────────
    def drawBackground(self, p: QPainter, rect: QRectF) -> None:  # noqa: N802
        p.fillRect(rect, theme.qcolor(theme.BG_WINDOW))
        step = GRID_STEP * (2 if self._zoom < 0.5 else 1)       # при сильном отдалении шаг ×2
        left = math.floor(rect.left() / step) * step
        top = math.floor(rect.top() / step) * step
        pts = QPolygonF()
        y = top
        while y < rect.bottom():
            x = left
            while x < rect.right():
                pts.append(QPointF(x, y))
                x += step
            y += step
        pen = p.pen()
        pen.setColor(theme.qcolor(theme.GRID_DOT))
        pen.setWidthF(2.0 if self._zoom >= 0.5 else 2.5)
        p.setPen(pen)
        p.drawPoints(pts)

    # ───────────── зум ─────────────
    @property
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, value: float, anchor_view_pos: QPoint | None = None) -> None:
        value = max(ZOOM_MIN, min(ZOOM_MAX, value))
        if abs(value - self._zoom) < 1e-9:
            return
        factor = value / self._zoom
        if anchor_view_pos is None:
            anchor_view_pos = self.viewport().rect().center()
        before = self.mapToScene(anchor_view_pos)
        self._zoom = value
        self.scale(factor, factor)
        after = self.mapToScene(anchor_view_pos)
        # удерживаем точку сцены под курсором (anchor) на месте прокруткой
        hb, vb = self.horizontalScrollBar(), self.verticalScrollBar()
        hb.setValue(round(hb.value() + (before.x() - after.x()) * self._zoom))
        vb.setValue(round(vb.value() + (before.y() - after.y()) * self._zoom))
        self.zoom_changed.emit(self._zoom)
        self.viewport().update()

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * 1.15)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / 1.15)

    def reset_zoom(self) -> None:
        self.set_zoom(1.0)

    def wheel_zoom(self, delta_y: int, global_pos) -> None:
        """Зум колесом (из inline-виджетов и Ctrl+колесо над канвой), anchor под курсором."""
        if delta_y == 0:
            return
        factor = 1.0015 ** delta_y
        self.set_zoom(self._zoom * factor, self.viewport().mapFromGlobal(global_pos))

    def wheelEvent(self, e) -> None:  # noqa: N802
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.wheel_zoom(e.angleDelta().y(), e.globalPosition().toPoint())
            e.accept()
        else:
            super().wheelEvent(e)

    # ───────────── пан ─────────────
    def _begin_pan(self, pos: QPoint) -> None:
        self._panning, self._pan_last = True, pos
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.MiddleButton or \
                (e.button() == Qt.MouseButton.LeftButton and self._space):
            self._begin_pan(e.position().toPoint())
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._panning:
            pos = e.position().toPoint()
            d = pos - self._pan_last
            self._pan_last = pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if self._panning and e.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton):
            self._panning = False
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor if self._space
                                      else Qt.CursorShape.ArrowCursor)
            e.accept()
            return
        super().mouseReleaseEvent(e)

    # ───────────── клавиатура (Delete / Esc / Space) ─────────────
    def keyPressEvent(self, e) -> None:  # noqa: N802
        sc = self.scene()
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space = True
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            e.accept()
            return
        if e.key() == Qt.Key.Key_Delete:
            sc.delete_selected()
            e.accept()
            return
        if e.key() == Qt.Key.Key_Escape:
            if sc.dragging:
                sc.cancel_drag()
            else:
                sc.clearSelection()
            e.accept()
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space = False
            if not self._panning:
                self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            e.accept()
            return
        super().keyReleaseEvent(e)

    def focusOutEvent(self, e) -> None:  # noqa: N802
        self._space = False
        super().focusOutEvent(e)

    # ───────────── drop из палитры ─────────────
    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasFormat(MIME_NODE):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasFormat(MIME_NODE):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasFormat(MIME_NODE):
            type_ = bytes(e.mimeData().data(MIME_NODE)).decode("utf-8")
            self.scene().add_node_at(type_, self.mapToScene(e.position().toPoint()))
            e.acceptProposedAction()
            self.setFocus()
        else:
            super().dropEvent(e)

    def visible_center_for_node(self) -> QPointF:
        """Левый верхний угол узла так, чтобы узел оказался в центре видимой области."""
        c = self.mapToScene(self.viewport().rect().center())
        return QPointF(c.x() - NODE_W / 2, c.y() - 28)
