"""ЕДИНСТВЕННЫЙ источник цветов и общего QSS (SPEC_UI п. 1–2).

Шрифты (решение пользователя): Geist для текста, Geist Mono для значений и кода.
Если Geist не вшился или не загрузился — деградация на Segoe UI / Consolas с теми же размерами.
Размеры шрифтов остаются по SPEC_UI (9 / 10 / 16 pt).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase

# ───────────── палитра (SPEC_UI п. 2) ─────────────
BG_WINDOW = "#1f2124"
BG_PANEL = "#26292c"
BG_ELEMENT = "#2e3236"
BG_ELEMENT_HOVER = "#3a3f44"
BG_ELEMENT_PRESSED = "#454b51"
BORDER = "#3a3f44"
BORDER_SUBTLE = "#2f3337"
TEXT_PRIMARY = "#e8eaed"
TEXT_SECONDARY = "#9aa0a6"
TEXT_MUTED = "#6f757c"
ACCENT = "#7d8ea3"
ACCENT_HOVER = "#8a9cb2"
DANGER = "#b97a7a"
GRID_DOT = "#2b2e31"

CATEGORY_COLORS = {
    "Sources": "#8296a8",
    "Extraction": "#8f9a86",
    "Logic": "#a89f8a",
    "Actions": "#9086a0",
    "Result": "#6f757c",
    "Custom": "#9aa0a6",
    "Data & code": "#7d8ea3",
}

# ───────────── шрифты ─────────────
_FONT_UI = "Segoe UI"
_FONT_MONO = "Consolas"
from ..paths import resource_path  # noqa: E402
_FONTS_DIR = resource_path("assets", "fonts")

PT_LABEL = 9      # служебные метки, чипы, подписи
PT_BASE = 10      # данные, заголовки узлов
PT_TITLE = 16     # название проекта
PT_PORT = 8       # подписи портов


def init_fonts() -> None:
    """Регистрирует вшитые Geist/Geist Mono; при неудаче остаются Segoe UI / Consolas."""
    global _FONT_UI, _FONT_MONO
    for ttf in sorted(_FONTS_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(ttf))
    families = set(QFontDatabase.families())
    if "Geist" in families:
        _FONT_UI = "Geist"
    if "Geist Mono" in families:
        _FONT_MONO = "Geist Mono"


def font_ui_name() -> str:
    return _FONT_UI


def font_mono_name() -> str:
    return _FONT_MONO


def ui_font(pt: float = PT_BASE, bold: bool = False) -> QFont:
    f = QFont(_FONT_UI)
    f.setPointSizeF(pt)
    f.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
    f.setItalic(False)
    return f


def mono_font(pt: float = PT_LABEL) -> QFont:
    f = QFont(_FONT_MONO)
    f.setPointSizeF(pt)
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setItalic(False)
    return f


def label_font() -> QFont:
    """Служебные подписи: uppercase 9 pt, letter-spacing 0.5 px."""
    f = ui_font(PT_LABEL)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.5)
    return f


# ───────────── утилиты цвета ─────────────
def qcolor(hex_: str) -> QColor:
    return QColor(hex_)


def mix(a: str, b: str, t: float) -> QColor:
    """Линейное смешение двух hex-цветов: t=0 → a, t=1 → b."""
    ca, cb = QColor(a), QColor(b)
    t = max(0.0, min(1.0, t))
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * t),
        round(ca.green() + (cb.green() - ca.green()) * t),
        round(ca.blue() + (cb.blue() - ca.blue()) * t),
    )


# ───────────── общий QSS ─────────────
def build_qss() -> str:
    return f"""
* {{ color: {TEXT_PRIMARY}; font-family: "{_FONT_UI}"; font-size: {PT_BASE}pt; }}
QMainWindow, QDialog, QMessageBox, #root {{ background: {BG_WINDOW}; }}
QLabel {{ background: transparent; }}
QLabel[muted="true"] {{ color: {TEXT_MUTED}; }}
QLabel[over="true"] {{ color: {DANGER}; }}

#sidebar, #palette, #paramsPanel {{ background: {BG_PANEL}; }}
#toolbar {{ background: {BG_PANEL}; }}

QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox {{
    background: {BG_ELEMENT}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px 8px;
    selection-background-color: {ACCENT}; selection-color: {BG_WINDOW};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}
QLineEdit:disabled, QPlainTextEdit:disabled {{ color: {TEXT_MUTED}; }}

QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}
QComboBox::drop-down {{ width: 20px; border: none; background: transparent; }}
QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
QComboBox QAbstractItemView {{
    background: {BG_ELEMENT}; border: 1px solid {BORDER}; outline: none;
    selection-background-color: {BG_ELEMENT_HOVER}; selection-color: {TEXT_PRIMARY};
}}

#titleEdit {{ background: transparent; border: 1px solid transparent; font-size: {PT_TITLE}pt;
              padding: 4px 8px; }}
#titleEdit:focus {{ border-color: {ACCENT}; background: transparent; }}
#ideaEdit, #descEdit {{ background: {BG_PANEL}; border: 1px solid transparent; border-radius: 8px;
              padding: 8px 12px; }}
#ideaEdit:focus, #descEdit:focus {{ border-color: {ACCENT}; }}

QPushButton {{ background: {BG_ELEMENT}; border: none; border-radius: 6px; padding: 8px 16px;
               min-width: 64px; }}
QPushButton:hover {{ background: {BG_ELEMENT_HOVER}; }}
QPushButton:pressed {{ background: {BG_ELEMENT_PRESSED}; }}

QToolTip {{ background: {BG_ELEMENT}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER};
            padding: 4px 8px; }}
QStatusBar {{ background: {BG_PANEL}; color: {TEXT_MUTED}; }}
QStatusBar QLabel {{ color: {TEXT_MUTED}; }}
QStatusBar::item {{ border: none; }}

QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ background: transparent; color: {TEXT_SECONDARY}; padding: 8px 16px;
                border: none; border-radius: 6px; margin: 8px 0 0 8px; }}
QTabBar::tab:hover {{ background: {BG_ELEMENT}; }}
QTabBar::tab:selected {{ background: {BG_ELEMENT_HOVER}; color: {TEXT_PRIMARY}; }}

QMenu {{ background: {BG_ELEMENT}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px; }}
QMenu::item {{ padding: 8px 16px; border-radius: 4px; }}
QMenu::item:selected {{ background: {BG_ELEMENT_HOVER}; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QAbstractScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {BG_ELEMENT}; border-radius: 4px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {BG_ELEMENT_HOVER}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; background: none; border: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ border-left: 2px solid transparent; margin: 2px 4px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {BG_ELEMENT_HOVER}; border-left: 2px solid {ACCENT}; }}
QListWidget::item:hover {{ background: {BG_ELEMENT}; }}
QGraphicsView {{ border: none; background: {BG_WINDOW}; }}
"""
