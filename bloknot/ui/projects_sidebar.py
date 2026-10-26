"""Сайдбар проектов: список карточек, создание, удаление (SPEC_UI п. 4)."""
from __future__ import annotations
from ..i18n import t

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMenu, QVBoxLayout, QWidget)

from . import theme
from ..services.project_service import ProjectSummary
from .widgets import Button, SectionLabel

CARD_H = 56


class _CardWidget(QWidget):
    """Карточка проекта: имя (bold) + первая строка идеи (эллипсис)."""

    def __init__(self, summary: ProjectSummary, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 8, 8)
        lay.setSpacing(2)
        self._name = QLabel(t(summary.name))
        f = theme.ui_font(theme.PT_BASE, bold=True)
        self._name.setFont(f)
        lay.addWidget(self._name)
        self._idea = QLabel(summary.idea_summary or " ")
        self._idea.setProperty("muted", True)
        self._idea.setFont(theme.ui_font(theme.PT_LABEL))
        lay.addWidget(self._idea)
        self.set_summary(summary)

    def set_summary(self, s: ProjectSummary) -> None:
        fm = QFontMetrics(self._name.font())
        self._name.setText(fm.elidedText(t(s.name), Qt.TextElideMode.ElideRight, 200))
        fm2 = QFontMetrics(self._idea.font())
        first = " ".join(s.idea_summary.split())
        self._idea.setText(fm2.elidedText(first, Qt.TextElideMode.ElideRight, 200))


class ProjectsSidebar(QWidget):
    project_selected = Signal(str)
    create_requested = Signal()
    delete_requested = Signal(str)          # main_window показывает диалог подтверждения

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(240)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        root.addWidget(SectionLabel(t("Projects")))
        new_btn = Button(t("+ New project"), "primary")
        new_btn.clicked.connect(self.create_requested)
        root.addWidget(new_btn)

        self.list = QListWidget()
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.currentItemChanged.connect(self._on_current)
        root.addWidget(self.list, 1)

        self._empty = QLabel(t("Create your first project"))
        self._empty.setProperty("muted", True)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)
        root.addWidget(self._empty)

        self._projects: list[ProjectSummary] = []
        self._suppress = False

    # ───────────── данные ─────────────
    def refresh(self, projects: list[ProjectSummary], selected_id: str | None = None) -> None:
        self._projects = projects
        self._suppress = True
        try:
            self.list.clear()
            for s in projects:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, s.id)
                card = _CardWidget(s)
                self.list.addItem(item)
                self.list.setItemWidget(item, card)
                item.setSizeHint(QSize(0, CARD_H))
            for i in range(self.list.count()):
                if self.list.item(i).data(Qt.ItemDataRole.UserRole) == selected_id:
                    self.list.setCurrentRow(i)
                    break
            else:
                self.list.setCurrentRow(-1)
        finally:
            self._suppress = False
        has = bool(projects)
        self.list.setVisible(has)
        self._empty.setVisible(not has)

    def current_id(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    # ───────────── события ─────────────
    def _on_current(self, cur, _prev) -> None:
        if self._suppress or cur is None:
            return
        self.project_selected.emit(cur.data(Qt.ItemDataRole.UserRole))

    def _context_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        act = menu.addAction(t("Delete"))
        act.setData(item.data(Qt.ItemDataRole.UserRole))
        font = theme.ui_font(theme.PT_BASE)
        menu.setFont(font)
        shown = menu.exec(self.list.mapToGlobal(pos))
        if shown is not None:
            self.delete_requested.emit(shown.data())
