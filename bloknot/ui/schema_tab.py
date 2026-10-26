"""Вкладка «Схема»: тулбар runtime + палитра · канва · панель параметров (SPEC_UI п. 5)."""
from __future__ import annotations
from ..i18n import t

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..services.flow_service import FlowService
from ..services.project_service import ProjectService
from . import theme
from .canvas.canvas_view import CanvasView
from .canvas.palette import Palette
from .canvas.scene import GraphScene
from .params_panel import ParamsPanel
from .widgets import Button, ToggleSwitch

EVAL_DEBOUNCE_MS = 200       # SPEC_FLOW п. 4
SAVE_DEBOUNCE_MS = 500       # SPEC_STORAGE п. 6


class SchemaTab(QWidget):
    message = Signal(str, int)
    saved = Signal()

    def __init__(self, service: ProjectService, flow: FlowService,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service, self.flow = service, flow
        self.message.connect(lambda *_: None)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── тулбар runtime (40 px) ──
        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        toolbar.setFixedHeight(40)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(12, 4, 12, 4)
        self._run_btn = Button(t("Recalculate all"), "primary", icon="play")
        self._run_btn.clicked.connect(self.evaluate_all)
        tb.addWidget(self._run_btn)
        self._live = ToggleSwitch(t("Auto"), checked=True)
        self._live.toggled.connect(self._on_live)
        tb.addWidget(self._live)
        clear_btn = Button(t("Clear values"), "secondary")
        clear_btn.clicked.connect(flow.clear_values)
        tb.addWidget(clear_btn)
        tb.addStretch(1)
        hint = QLabel(t("Drag a block · output → input to link · Ctrl+wheel zoom · Delete to remove"))
        hint.setProperty("muted", True)
        hint.setFont(theme.ui_font(theme.PT_LABEL))
        tb.addWidget(hint)
        root.addWidget(toolbar)

        # ── три колонки ──
        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(0)

        self.scene = GraphScene(service, flow)
        self.view = CanvasView(self.scene)
        self.palette = Palette()
        self.params = ParamsPanel(service)

        columns.addWidget(self.palette)
        columns.addWidget(self.view, 1)
        columns.addWidget(self.params)
        root.addLayout(columns, 1)

        # ── таймеры debounce (их держит UI — SPEC_FLOW п. 4) ──
        self._eval_timer = QTimer(self)
        self._eval_timer.setSingleShot(True)
        self._eval_timer.setInterval(EVAL_DEBOUNCE_MS)
        self._eval_timer.timeout.connect(flow.evaluate_pending)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(service.flush)

        # ── колбэки движка/сервиса ──
        service.on_dirty = self._save_timer.start
        service.on_eval = self._eval_timer.start
        service.on_message = lambda text, ms: self.message.emit(text, ms)
        service.on_saved = lambda: self.saved.emit()

        # ── сцена ↔ панель ──
        self.scene.message.connect(lambda text: self.message.emit(text, 3000))
        self.scene.param_edited.connect(self.params.sync_param)      # inline → панель
        self.scene.node_activated.connect(self._activate_node)
        self.scene.selectionChanged.connect(self._on_selection)
        self.scene.values_changed.connect(lambda _ids: self.params.refresh_error())
        self.params.duplicate_requested.connect(
            lambda _nid: self.scene.duplicate_selected())
        self.params.delete_requested.connect(
            lambda _nid: self.scene.delete_selected())
        self.palette.insert_requested.connect(self.add_node_centered)

    # ───────────── загрузка проекта ─────────────
    def load_project(self, project) -> None:
        self.params.show_node(None)
        self.scene.load(project)
        self._eval_timer.start()                 # пересчёт по debounce после загрузки

    # ───────────── действия ─────────────
    def add_node_centered(self, type_: str) -> None:
        self.scene.add_node_at(type_, self.view.visible_center_for_node())

    def evaluate_all(self) -> None:
        self.flow.evaluate_now()

    def duplicate_selected(self) -> None:
        self.scene.duplicate_selected()

    def delete_selected(self) -> None:
        self.scene.delete_selected()

    def zoom_in(self) -> None:
        self.view.zoom_in()

    def zoom_out(self) -> None:
        self.view.zoom_out()

    def reset_zoom(self) -> None:
        self.view.reset_zoom()

    # ───────────── внутреннее ─────────────
    def _on_live(self, on: bool) -> None:
        self.flow.set_live(on)
        self.scene.set_live(on)

    def _activate_node(self, node_id: str) -> None:
        self.params.show_node(node_id)

    def _on_selection(self) -> None:
        items = [i for i in self.scene.selectedItems() if hasattr(i, "node")]
        if len(items) == 1:
            self.params.show_node(items[0].node.id)
        elif self.params.node_id is not None:
            # выбранный узел мог быть удалён — иначе панель не трогаем
            if items:
                return
            self.params.show_node(None)
