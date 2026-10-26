"""Панель параметров выбранного узла (SPEC_UI п. 5.6)."""
from __future__ import annotations
from ..i18n import t

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget)

from ..core.node_types import NodeSpec, block_syntax, block_usage, get_spec
from . import theme
from .widgets import Button, SectionLabel, connect_change, make_param_widget


class ParamsPanel(QWidget):
    """Справа на вкладке «Схема»: все параметры узла + дублирование/удаление."""

    duplicate_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("paramsPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.service = service
        self.node_id: str | None = None
        self._spec: NodeSpec | None = None
        self._widgets: dict[str, QWidget] = {}
        self._loading = False

        self.setFixedWidth(260)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # пустое состояние
        self._empty = QLabel(t("Select a block"))
        self._empty.setProperty("muted", True)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._empty)

        # тело панели
        self._body = QWidget()
        body = QVBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)

        self._title = QLineEdit()
        self._title.setPlaceholderText(t("Node name"))
        self._title.textEdited.connect(self._on_title)
        body.addWidget(self._title)

        self._type_label = QLabel()
        self._type_label.setFont(theme.mono_font(theme.PT_LABEL))
        self._type_label.setProperty("muted", True)
        body.addWidget(self._type_label)

        self._form_host = QWidget()
        self._form = QVBoxLayout(self._form_host)
        self._form.setContentsMargins(0, 4, 0, 0)
        self._form.setSpacing(8)
        body.addWidget(self._form_host)

        body.addStretch(1)

        self._error = QLabel()
        self._error.setProperty("over", True)
        self._error.setWordWrap(True)
        self._error.hide()
        body.addWidget(self._error)

        buttons = QHBoxLayout()
        self._dup_btn = Button(t("Duplicate"), "secondary")
        self._dup_btn.clicked.connect(self._on_duplicate)
        self._del_btn = Button(t("Delete"), "danger")
        self._del_btn.clicked.connect(self._on_delete)
        buttons.addWidget(self._dup_btn)
        buttons.addWidget(self._del_btn)
        body.addLayout(buttons)

        root.addWidget(self._body)

        self.show_node(None)

    # ───────────── отображение узла ─────────────
    def show_node(self, node_id: str | None) -> None:
        self.node_id = node_id
        self._widgets.clear()
        while self._form.count():
            item = self._form.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        node = self.service.node(node_id) if node_id else None
        has = node is not None
        self._body.setVisible(has)
        self._empty.setVisible(not has)
        if not has:
            self._spec = None
            return

        self._loading = True
        try:
            self._spec = get_spec(node.type)
            self._title.setText(node.title)
            self._type_label.setText(self._spec.type)
            for key, ps in self._spec.params.items():
                self._form.addWidget(SectionLabel(t(ps.label)))
                w = make_param_widget(ps, node.params.get(key, ps.default), inline=False)
                connect_change(w, ps, lambda v, k=key: self._on_param(k, v))
                self._form.addWidget(w)
                self._widgets[key] = w
            self._add_help(node.type)
        finally:
            self._loading = False
        self.refresh_error()

    def _add_help(self, type_: str) -> None:
        """Справка внизу панели: синтаксис, как использовать, пример связи (SPEC_UI)."""
        syntax, _ = block_syntax(type_)
        how, link = block_usage(type_)
        for label, text in ((t("Syntax"), syntax), (t("How to use"), how), (t("Link example"), link)):
            if not text:
                continue
            self._form.addWidget(SectionLabel(label))
            body_label = QLabel(text)
            body_label.setWordWrap(True)
            body_label.setProperty("muted", label == t("Syntax"))
            body_label.setFont(theme.mono_font(theme.PT_LABEL) if label != t("How to use") else theme.ui_font(theme.PT_BASE))
            self._form.addWidget(body_label)

    def sync_param(self, node_id: str, key: str) -> None:
        """Параметр изменён inline-виджетом — синхронизировать панель (без петли)."""
        if node_id != self.node_id or key not in self._widgets:
            return
        node = self.service.node(node_id)
        from .widgets import write_value
        if node is not None:
            write_value(self._widgets[key], self._spec.params[key], node.params.get(key))

    def refresh_error(self) -> None:
        if self.node_id is None:
            self._error.hide()
            return
        st = self.service.flow.get_state(self.node_id)
        if st.error:
            self._error.setText(st.error)
            self._error.show()
        else:
            self._error.hide()

    # ───────────── события ─────────────
    def _on_param(self, key: str, value) -> None:
        if self._loading or self.node_id is None:
            return
        self.service.set_param(self.node_id, key, value)
        self.refresh_error()

    def _on_title(self, text: str) -> None:
        if self.node_id is None:
            return
        self.service.set_title(self.node_id, text)

    def _on_duplicate(self) -> None:
        if self.node_id is not None:
            self.duplicate_requested.emit(self.node_id)

    def _on_delete(self) -> None:
        if self.node_id is not None:
            self.delete_requested.emit(self.node_id)
