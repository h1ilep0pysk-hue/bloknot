"""Каркас главного окна: сайдбар + вкладки «Идея»/«Схема» + статус-бар (SPEC_UI п. 3, 7, 8)."""
from __future__ import annotations
from ..i18n import t

from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QMainWindow, QMessageBox,
                               QStatusBar, QTabWidget, QWidget)

from .. import i18n
from ..services.export_service import export_agent, export_markdown
from ..services.project_service import ProjectService
from . import theme
from .idea_tab import IdeaTab
from .projects_sidebar import ProjectsSidebar
from .schema_tab import SchemaTab


class MainWindow(QMainWindow):
    def __init__(self, service: ProjectService, flow, db_memory: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.flow = flow

        self.resize(1280, 800)
        self.setMinimumSize(960, 640)
        self._update_title()

        central = QWidget()
        central.setObjectName("root")
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── сайдбар ──
        self.sidebar = ProjectsSidebar()
        self.sidebar.create_requested.connect(self.create_project)
        self.sidebar.project_selected.connect(self.open_project)
        self.sidebar.delete_requested.connect(self.confirm_delete)
        lay.addWidget(self.sidebar)

        # ── вкладки ──
        self.tabs = QTabWidget()
        self.idea_tab = IdeaTab(service)
        self.schema_tab = SchemaTab(service, flow)
        self.tabs.addTab(self.idea_tab, t("Idea"))
        self.tabs.addTab(self.schema_tab, t("Schema"))
        lay.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        # ── статус-бар (28 px, только сообщения — SPEC_UI п. 8) ──
        sb = QStatusBar()
        sb.setFixedHeight(28)
        self.setStatusBar(sb)
        self.schema_tab.message.connect(lambda text, ms: sb.showMessage(text, ms))
        self.schema_tab.saved.connect(lambda: sb.showMessage(t("Saved"), 2000))
        if db_memory:
            sb.showMessage(t("Database unavailable — changes are not saved"), 6000)

        # ── меню «Настройки → Язык» ──
        self._build_menu()

        # ── горячие клавиши (SPEC_UI п. 7) ──
        self._shortcut("Ctrl+N", self.create_project)
        self._shortcut("Ctrl+E", self.export_markdown)
        self._shortcut("Ctrl+Shift+E", self.export_for_agent)
        self._shortcut("Ctrl+=", self.schema_tab.zoom_in)
        self._shortcut("Ctrl+-", self.schema_tab.zoom_out)
        self._shortcut("Ctrl+0", self.schema_tab.reset_zoom)
        self._shortcut("F5", self.schema_tab.evaluate_all)
        self._shortcut("Ctrl+D", self.schema_tab.duplicate_selected)

        self.idea_tab._empty_btn.clicked.connect(self.create_project)
        self.idea_tab.export_requested.connect(self.export_markdown)
        self.idea_tab.export_agent_requested.connect(self.export_for_agent)

        self.refresh_projects()

    # ───────────── проекты ─────────────
    def refresh_projects(self) -> None:
        projects = self.service.list_projects()
        current = self.service.current.id if self.service.current else None
        self.sidebar.refresh([p for p in projects], selected_id=current)
        self._load_current()

    def _load_current(self) -> None:
        project = self.service.current
        self.idea_tab.load_project(project)
        self.schema_tab.load_project(project)
        self._update_title()

    def create_project(self) -> None:
        project = self.service.create_project()
        self.refresh_projects()
        self.sidebar_list_select(project.id)
        self.tabs.setCurrentIndex(0)                 # сразу на «Идею» — ввести название

    def open_project(self, project_id: str) -> None:
        self.service.open_project(project_id)
        self._load_current()

    def sidebar_list_select(self, project_id: str) -> None:
        lst = self.sidebar.list
        for i in range(lst.count()):
            if lst.item(i).data(0x0100) == project_id:      # Qt.ItemDataRole.UserRole
                lst.setCurrentRow(i)
                return

    def confirm_delete(self, project_id: str) -> None:
        summary = next((p for p in self.service.list_projects() if p.id == project_id), None)
        name = summary.name if summary else "проект"
        answer = QMessageBox.question(
            self, "Удаление проекта", t('Delete project "{name}"?').format(name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.service.delete_project(project_id)
        remaining = self.service.list_projects()
        if remaining:
            self.service.open_project(remaining[0].id)
        self.refresh_projects()

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu(t("Settings"))
        lang_menu = menu.addMenu(t("Language"))
        group = QActionGroup(self)
        group.setExclusive(True)
        for code, label in i18n.LANGUAGES.items():
            act = QAction(label, self, checkable=True)
            act.setChecked(code == i18n.get_language())
            act.triggered.connect(lambda _checked=False, c=code: self._set_language(c))
            group.addAction(act)
            lang_menu.addAction(act)

    def _set_language(self, code: str) -> None:
        i18n.save_language(code)
        self.statusBar().showMessage(t("Restart Bloknot to apply the language"), 6000)

    # ───────────── экспорт ─────────────
    def export_markdown(self) -> None:
        p = self.service.current
        if p is None:
            self.statusBar().showMessage(t("No project is open"), 3000)
            return
        self.service.flush(force=True)
        path, _ = QFileDialog.getSaveFileName(self, t("Export Markdown"), f"{p.name}.md",
                                              "Markdown (*.md)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(export_markdown(p))
        except OSError:
            self.statusBar().showMessage(t("Could not save the file"), 4000)
            return
        self.statusBar().showMessage(t("Exported"), 2000)

    def export_for_agent(self) -> None:
        p = self.service.current
        if p is None:
            self.statusBar().showMessage(t("No project is open"), 3000)
            return
        self.service.flush(force=True)
        path, _ = QFileDialog.getSaveFileName(self, t("Export for AI"), f"{p.name}_архитектура.md",
                                              "Markdown (*.md)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(export_agent(p))
        except OSError:
            self.statusBar().showMessage(t("Could not save the file"), 4000)
            return
        self.statusBar().showMessage(t("Exported for AI"), 2000)

    # ───────────── прочее ─────────────
    def _update_title(self) -> None:
        name = self.service.current.name if self.service.current else None
        self.setWindowTitle(f"Bloknot — {t(name)}" if name else "Bloknot")

    def _shortcut(self, keys: str, cb) -> None:
        QShortcut(QKeySequence(keys), self, cb)

    def closeEvent(self, event) -> None:  # noqa: N802
        # финальная немедленная запись без debounce (SPEC_STORAGE п. 6)
        self.service.flush(force=True)
        super().closeEvent(event)
