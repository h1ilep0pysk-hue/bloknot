"""Сборка приложения: БД → сервисы → окно (ARCHITECTURE п. 6)."""
from __future__ import annotations

import logging
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import i18n
from .paths import resource_path
from .ui import theme
from .storage import db
from .storage.project_repository import ProjectRepository
from .services.flow_service import FlowService
from .services.project_service import ProjectService
from .ui.main_window import MainWindow

log = logging.getLogger("bloknot")


def _open_storage():
    """Файл БД; недоступен → работа в памяти с предупреждением (SPEC_STORAGE п. 8)."""
    try:
        return db.connect(), False
    except Exception:  # noqa: BLE001 — sqlite3.Error и прочее
        log.exception("база данных недоступна")
        return db.connect_memory(), True


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Bloknot")
    i18n.init_from_settings()          # язык из data/settings.json — до создания окна
    icon = resource_path("assets", "icon", "icon.ico")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    app.setStyle("Fusion")
    theme.init_fonts()
    app.setStyleSheet(theme.build_qss())

    conn, db_memory = _open_storage()
    flow = FlowService()
    service = ProjectService(ProjectRepository(conn), flow)

    win = MainWindow(service, flow, db_memory=db_memory)
    win.show()

    # открыть последний проект или создать первый
    projects = service.list_projects()
    if projects:
        service.open_project(projects[0].id)
        win.refresh_projects()
    else:
        service.create_project()
        win.refresh_projects()

    return app.exec()
