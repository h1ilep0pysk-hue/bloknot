"""Палитра блоков с drag-исходником (SPEC_UI п. 5.2)."""
from __future__ import annotations
from ...i18n import t

from PySide6.QtCore import QMimeData, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QDrag, QPainter
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from ...core.node_types import NodeSpec, palette_groups
from .. import theme
from ..widgets import SectionLabel, make_anim
from .canvas_view import MIME_NODE

ROW_H = 32
DRAG_THRESHOLD = 5


class PaletteRow(QWidget):
    insert_requested = Signal(str)

    def __init__(self, spec: NodeSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.spec = spec
        self._t = 0.0
        self._press: QPoint | None = None
        self._anim = make_anim(self, self._set_t)
        self.setFixedHeight(ROW_H)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(t("Drag onto the canvas or double-click"))

    def _set_t(self, v: float) -> None:
        self._t = v
        self.update()

    def _fade(self, to: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._t)
        self._anim.setEndValue(to)
        self._anim.start()

    def enterEvent(self, e) -> None:  # noqa: N802
        self._fade(1.0)

    def leaveEvent(self, e) -> None:  # noqa: N802
        self._fade(0.0)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        if self._t > 0:                                  # фон прозрачный, hover — BG_ELEMENT
            c = theme.qcolor(theme.BG_ELEMENT)
            c.setAlphaF(self._t)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(r.adjusted(4, 0, -4, 0), 6, 6)
        dot = theme.CATEGORY_COLORS.get(self.spec.category, theme.TEXT_MUTED)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor(dot))
        p.drawEllipse(QRectF(16, r.center().y() - 3, 6, 6))
        p.setFont(theme.ui_font(theme.PT_BASE))
        p.setPen(theme.qcolor(theme.TEXT_PRIMARY))
        fm = p.fontMetrics()
        p.drawText(QRectF(30, 0, r.width() - 40, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   fm.elidedText(t(self.spec.title), Qt.TextElideMode.ElideRight, int(r.width() - 40)))

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.position().toPoint()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._press is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        if (e.position().toPoint() - self._press).manhattanLength() <= DRAG_THRESHOLD:
            return
        self._press = None
        mime = QMimeData()
        mime.setData(MIME_NODE, self.spec.type.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        pm = self.grab()
        drag.setPixmap(pm)
        drag.setHotSpot(QPoint(20, ROW_H // 2))
        drag.exec(Qt.DropAction.CopyAction)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        self._press = None

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: N802
        self._press = None
        self.insert_requested.emit(self.spec.type)


class Palette(QWidget):
    insert_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("palette")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(220)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(area)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 12, 0, 12)
        lay.setSpacing(0)
        for i, (cat, specs) in enumerate(palette_groups()):
            lbl = SectionLabel(t(cat))
            lbl.setContentsMargins(16, 24 if i else 4, 16, 4)
            lay.addWidget(lbl)
            for spec in specs:
                row = PaletteRow(spec)
                row.insert_requested.connect(self.insert_requested)
                lay.addWidget(row)
        lay.addStretch(1)
        area.setWidget(body)
