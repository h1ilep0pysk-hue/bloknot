"""Вкладка «Идея»: название, краткая идея ≤280, подробное описание (SPEC_UI п. 6)."""
from __future__ import annotations
from ..i18n import t

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QStackedLayout, QVBoxLayout, QWidget)

from ..services.project_service import IDEA_LIMIT
from . import theme
from .widgets import Button, SectionLabel


class IdeaTab(QWidget):
    export_requested = Signal()
    export_agent_requested = Signal()

    def __init__(self, service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self._loading = False

        stack = QStackedLayout(self)
        stack.setContentsMargins(0, 0, 0, 0)

        # ── пустое состояние ──
        empty_host = QWidget()
        empty = QVBoxLayout(empty_host)
        empty.addStretch(1)
        lbl = QLabel(t("Create your first project"))
        lbl.setProperty("muted", True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(lbl)
        btn = Button(t("+ New project"), "primary")
        btn.clicked.connect(lambda: None)          # подключается main_window через сигналы
        self._empty_btn = btn
        empty.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
        empty.addStretch(1)
        stack.addWidget(empty_host)

        # ── форма ──
        form = QWidget()
        root = QVBoxLayout(form)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)

        self._title = QLineEdit()
        self._title.setObjectName("titleEdit")
        self._title.setPlaceholderText(t("Project name"))
        self._title.textEdited.connect(self._on_title)
        root.addWidget(self._title)

        idea_head = QHBoxLayout()
        idea_head.addWidget(SectionLabel(t("Short idea")))
        idea_head.addStretch(1)
        self._counter = QLabel(f"0 / {IDEA_LIMIT}")
        self._counter.setProperty("muted", True)
        self._counter.setFont(theme.ui_font(theme.PT_LABEL))
        idea_head.addWidget(self._counter)
        root.addLayout(idea_head)

        self._idea = QPlainTextEdit()
        self._idea.setObjectName("ideaEdit")
        self._idea.setFixedHeight(64)
        self._idea.setPlaceholderText(t("One or two sentences: what the app is and why"))
        self._idea.textChanged.connect(self._on_idea)
        root.addWidget(self._idea)

        desc_head = QHBoxLayout()
        desc_head.addWidget(SectionLabel(t("Detailed description")))
        desc_head.addStretch(1)
        export_btn = Button(t("Export Markdown"), "secondary")
        export_btn.clicked.connect(self.export_requested)
        desc_head.addWidget(export_btn)
        agent_btn = Button(t("Export for AI"), "secondary")
        agent_btn.clicked.connect(self.export_agent_requested)
        desc_head.addWidget(agent_btn)
        root.addLayout(desc_head)

        self._desc = QPlainTextEdit()
        self._desc.setObjectName("descEdit")
        self._desc.setPlaceholderText(t("How it works, what architecture, where data comes from…"))
        self._desc.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        root.addWidget(self._desc, 1)

        stack.addWidget(form)
        self._form_index = 1
        self._empty_index = 0

    def load_project(self, project) -> None:
        """Заполняет поля; пока проект не открыт — пустое состояние."""
        self._loading = True
        try:
            if project is None:
                self.setCurrentEmpty(True)
                return
            self.setCurrentEmpty(False)
            self._title.setText(project.name)
            self._idea.setPlainText(project.idea_summary)
            self._desc.setPlainText(project.description)
            self._update_counter(project.idea_summary)
        finally:
            self._loading = False

    def setCurrentEmpty(self, empty: bool) -> None:  # noqa: N802
        self.layout().setCurrentIndex(self._empty_index if empty else self._form_index)

    # ───────────── события ─────────────
    def _on_title(self, text: str) -> None:
        if not self._loading:
            self.service.update_text(name=text)

    def _on_idea(self) -> None:
        text = self._idea.toPlainText()
        self._update_counter(text)
        if not self._loading:
            self.service.update_text(idea=text)

    def _update_counter(self, text: str) -> None:
        self._counter.setText(f"{len(text)} / {IDEA_LIMIT}")
        self._counter.setProperty("over", len(text) > IDEA_LIMIT)
        self._counter.setProperty("muted", len(text) <= IDEA_LIMIT)
        self._counter.style().unpolish(self._counter)
        self._counter.style().polish(self._counter)
