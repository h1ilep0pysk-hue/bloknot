"""Общие виджеты: кнопка, тумблер, spin, combo, метки, фабрика виджетов параметров.

Анимации — только микро (hover/focus/обновление чипа), 150–200 мс, без перемещений
и без изменения геометрии (решение пользователя; SPEC_UI запрещает остальное).
"""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QWidget)

from ..core.node_types import ParamSpec
from . import theme

HOVER_MS = 150
_EASE = QEasingCurve.Type.OutCubic


def make_anim(owner, on_value: Callable[[float], None], ms: int = HOVER_MS) -> QVariantAnimation:
    anim = QVariantAnimation(owner)
    anim.setDuration(ms)
    anim.setEasingCurve(QEasingCurve(_EASE))
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.valueChanged.connect(lambda v: on_value(float(v)))
    return anim


class Button(QPushButton):
    """Плоская скруглённая кнопка. kind: primary | secondary | danger | menu_danger."""

    def __init__(self, text: str, kind: str = "secondary", icon: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._kind, self._icon = kind, icon
        self._t = 0.0
        self._anim = make_anim(self, self._set_t)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setFont(theme.ui_font(theme.PT_BASE, bold=True))
        if kind == "menu_danger":
            self.setFixedHeight(32)

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
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:  # noqa: N802
        self._fade(0.0)
        super().leaveEvent(e)

    def sizeHint(self) -> QSize:  # noqa: N802
        w = self.fontMetrics().horizontalAdvance(self.text()) + 32
        if self._icon:
            w += 20
        return QSize(max(w, 64), 36 if self._kind != "menu_danger" else 32)

    def _colors(self) -> tuple[QColor, QColor]:
        k = self._kind
        if k == "primary":
            base, hover, pressed, text = theme.ACCENT, theme.ACCENT_HOVER, theme.ACCENT, theme.BG_WINDOW
        elif k == "menu_danger":
            base, hover, pressed, text = theme.BG_ELEMENT, theme.BG_ELEMENT_HOVER, theme.BG_ELEMENT_PRESSED, theme.DANGER
        elif k == "danger":
            base, hover, pressed, text = theme.BG_ELEMENT, theme.BG_ELEMENT_HOVER, theme.BG_ELEMENT_PRESSED, theme.DANGER
        else:
            base, hover, pressed, text = theme.BG_ELEMENT, theme.BG_ELEMENT_HOVER, theme.BG_ELEMENT_PRESSED, theme.TEXT_PRIMARY
        bg = theme.qcolor(pressed) if self.isDown() else theme.mix(base, hover, self._t)
        return bg, theme.qcolor(text)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg, fg = self._colors()
        r = QRectF(self.rect())
        if not self.isEnabled():
            p.setOpacity(0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, 6, 6)
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(theme.qcolor(theme.ACCENT if self._kind != "primary" else theme.TEXT_PRIMARY), 1))
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        p.setFont(self.font())
        p.setPen(fg)
        text_rect = r
        if self._icon == "play":
            fm = self.fontMetrics()
            tw = fm.horizontalAdvance(self.text())
            total = 10 + 8 + tw
            x0 = r.center().x() - total / 2
            cy = r.center().y()
            tri = QPolygonF([QPointF(x0, cy - 5), QPointF(x0, cy + 5), QPointF(x0 + 9, cy)])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fg)
            p.drawPolygon(tri)
            p.setPen(fg)
            text_rect = QRectF(x0 + 18, r.top(), tw + 4, r.height())
            p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
            return
        if self._kind == "menu_danger":
            text_rect = r.adjusted(12, 0, -12, 0)
            p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        else:
            p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.text())


class ToggleSwitch(QWidget):
    """Тумблер с подписью справа («Авто»). Положение ручки меняется мгновенно, цвет дорожки — 150 мс."""

    toggled = Signal(bool)

    def __init__(self, text: str, checked: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text, self._checked = text, checked
        self._t = 1.0 if checked else 0.0
        self._anim = make_anim(self, self._set_t)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setFont(theme.ui_font(theme.PT_BASE))

    def _set_t(self, v: float) -> None:
        self._t = v
        self.update()

    def isChecked(self) -> bool:  # noqa: N802
        return self._checked

    def setChecked(self, on: bool) -> None:  # noqa: N802
        if on == self._checked:
            return
        self._checked = on
        self._anim.stop()
        self._anim.setStartValue(self._t)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()
        self.toggled.emit(on)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(32 + 8 + self.fontMetrics().horizontalAdvance(self._text) + 4, 24)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.setChecked(not self._checked)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.setChecked(not self._checked)
        else:
            super().keyPressEvent(e)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cy = self.height() / 2
        track = QRectF(0, cy - 9, 32, 18)
        p.setBrush(theme.mix(theme.BG_ELEMENT, theme.ACCENT, self._t))
        p.setPen(QPen(theme.qcolor(theme.ACCENT if self.hasFocus() else theme.BORDER), 1))
        p.drawRoundedRect(track.adjusted(0.5, 0.5, -0.5, -0.5), 8.5, 8.5)
        knob_x = 3 + (14 if self._checked else 0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor(theme.BG_WINDOW if self._checked else theme.TEXT_SECONDARY))
        p.drawEllipse(QRectF(knob_x, cy - 6, 12, 12))
        p.setPen(theme.qcolor(theme.TEXT_PRIMARY))
        p.setFont(self.font())
        p.drawText(QRectF(40, 0, self.width() - 40, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)


class SectionLabel(QLabel):
    """Служебная метка: uppercase, 9 pt, TEXT_MUTED, letter-spacing 0.5 px."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text.upper(), parent)
        self.setFont(theme.label_font())
        self.setProperty("muted", True)


class FloatSpin(QDoubleSpinBox):
    """Числовое поле без кнопок: показывает «2», «0.3333»; принимает запятую как точку."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDecimals(10)
        self.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.setKeyboardTracking(True)

    def textFromValue(self, v: float) -> str:  # noqa: N802
        return f"{v:.10g}"

    def valueFromText(self, text: str) -> float:  # noqa: N802
        try:
            return float(text.strip().replace(",", "."))
        except ValueError:
            return self.value()

    def validate(self, text: str, pos: int):  # noqa: A003
        return super().validate(text.replace(",", "."), pos)


class ComboBox(QComboBox):
    """QComboBox со стрелкой, нарисованной монохромным штрихом TEXT_SECONDARY."""

    def paintEvent(self, e) -> None:  # noqa: N802
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x, y = self.width() - 14, self.height() / 2
        path = QPainterPath()
        path.moveTo(x - 3.5, y - 1.5)
        path.lineTo(x, y + 2)
        path.lineTo(x + 3.5, y - 1.5)
        pen = QPen(theme.qcolor(theme.TEXT_SECONDARY), 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPath(path)

    def wheelEvent(self, e) -> None:  # noqa: N802
        e.ignore()           # колесо не меняет значение случайно


# ───────────── фабрика виджетов параметров (канва и панель используют одну) ─────────────
LINE_H = 22
ROW_H = 14


def make_param_widget(ps: ParamSpec, value: Any, inline: bool) -> QWidget:
    """Создаёт виджет по ParamSpec. inline=True — компактные размеры из SPEC_UI п. 5.4."""
    w: QWidget
    if ps.widget == "spin":
        w = FloatSpin()
        w.setRange(ps.min, ps.max)
        w.setSingleStep(ps.step)
        if inline:
            w.setFixedSize(70, LINE_H)
    elif ps.widget == "combo":
        w = ComboBox()
        w.addItems([str(o) for o in (ps.options or [])])
        if inline:
            w.setFixedSize(80, LINE_H)
    elif ps.widget == "line":
        w = QLineEdit()
        w.setPlaceholderText(ps.placeholder)
        if inline:
            w.setFixedSize(130, LINE_H)
    else:  # text | code
        w = QPlainTextEdit()
        w.setPlaceholderText(ps.placeholder)
        w.setTabChangesFocus(True)
        if ps.widget == "code":
            w.setFont(theme.mono_font(theme.PT_LABEL))
        rows = max(1, ps.rows)
        if inline:
            w.setFixedSize(160, rows * ROW_H + 8)
        else:
            w.setFixedHeight(rows * 18 + 14)
    if inline:
        # компактные отступы, чтобы строка 22 px вмещала текст 9–10 pt
        w.setStyleSheet("padding: 1px 6px;")
        if ps.widget == "combo":
            w.setStyleSheet("padding: 1px 6px; padding-right: 18px;")
        elif ps.widget in ("text", "code"):
            w.setStyleSheet("padding: 2px 4px;")
    write_value(w, ps, value)
    return w


def read_value(w: QWidget, ps: ParamSpec) -> Any:
    if ps.widget == "spin":
        return float(w.value())             # type: ignore[attr-defined]
    if ps.widget == "combo":
        return w.currentText()              # type: ignore[attr-defined]
    if ps.widget == "line":
        return w.text()                     # type: ignore[attr-defined]
    return w.toPlainText()                  # type: ignore[attr-defined]


def write_value(w: QWidget, ps: ParamSpec, value: Any) -> None:
    """Записывает значение в виджет без испускания сигналов (нет петли виджет ↔ модель)."""
    was = w.blockSignals(True)
    try:
        if ps.widget == "spin":
            try:
                w.setValue(float(value))        # type: ignore[attr-defined]
            except (TypeError, ValueError):
                w.setValue(float(ps.default))   # type: ignore[attr-defined]
        elif ps.widget == "combo":
            text = str(value)
            idx = w.findText(text)              # type: ignore[attr-defined]
            if idx < 0:
                w.addItem(text)                 # type: ignore[attr-defined]
                idx = w.findText(text)          # type: ignore[attr-defined]
            w.setCurrentIndex(idx)              # type: ignore[attr-defined]
        elif ps.widget == "line":
            if w.text() != str(value or ""):    # type: ignore[attr-defined]
                w.setText(str(value or ""))     # type: ignore[attr-defined]
        else:
            if w.toPlainText() != str(value or ""):     # type: ignore[attr-defined]
                w.setPlainText(str(value or ""))        # type: ignore[attr-defined]
    finally:
        w.blockSignals(was)


def connect_change(w: QWidget, ps: ParamSpec, cb: Callable[[Any], None]) -> None:
    if ps.widget == "spin":
        w.valueChanged.connect(lambda v: cb(float(v)))                  # type: ignore[attr-defined]
    elif ps.widget == "combo":
        w.currentTextChanged.connect(lambda t: cb(t))                   # type: ignore[attr-defined]
    elif ps.widget == "line":
        w.textEdited.connect(lambda t: cb(t))                           # type: ignore[attr-defined]
    else:
        w.textChanged.connect(lambda: cb(w.toPlainText()))              # type: ignore[attr-defined]
