"""Исполняющий движок dataflow (SPEC_FLOW). Не импортирует PySide6."""
from __future__ import annotations

import importlib.util
import logging
from typing import Any, Callable

from ..core.models import Edge, Node, NodeRuntime, SchemaGraph
from ..core.node_types import SAFE_BUILTINS, get_spec, run_eval  # noqa: F401 (реэкспорт, SPEC_FLOW п. 9)
from ..core.ports import FlowError, coerce
from ..core.validation import topo_sort

log = logging.getLogger("bloknot.flow")
MAX_REPR = 1000


class FlowService:
    def __init__(self) -> None:
        self.schema: SchemaGraph = SchemaGraph()
        self.state: dict[str, NodeRuntime] = {}
        self.pending: set[str] = set()
        self.live: bool = True
        self._listeners: list[Callable[[list[str]], None]] = []
        # SPEC_FLOW п. 11: проверка один раз при старте, результат кэшируется
        self.has_numpy: bool = importlib.util.find_spec("numpy") is not None

    # ───────────── подключение ─────────────
    def set_schema(self, schema: SchemaGraph) -> None:
        self.schema = schema
        self.state = {n.id: NodeRuntime(outputs=None, error=None, dirty=True) for n in schema.nodes}
        self.pending.clear()

    def init_runtime(self, schema: SchemaGraph, runtime_json: dict | None = None) -> None:
        self.set_schema(schema)
        if runtime_json:
            self.restore_from_repr(runtime_json)

    def register_listener(self, cb: Callable[[list[str]], None]) -> None:
        self._listeners.append(cb)

    def set_live(self, on: bool) -> None:
        self.live = bool(on)

    def get_state(self, node_id: str) -> NodeRuntime:
        st = self.state.get(node_id)
        if st is None:
            st = self.state[node_id] = NodeRuntime(outputs=None, error=None, dirty=True)
        return st

    def forget(self, node_id: str) -> None:
        self.state.pop(node_id, None)
        self.pending.discard(node_id)

    # ───────────── инвалидация ─────────────
    def invalidate(self, node_id: str) -> None:
        if node_id not in self._nodes():
            return
        self.pending.add(node_id)
        marked = self._descendants({node_id})
        for n in marked:
            self.get_state(n).dirty = True
        self._notify(list(marked))

    def invalidate_all(self) -> None:
        ids = [n.id for n in self.schema.nodes]
        self.pending.update(ids)
        for i in ids:
            self.get_state(i).dirty = True
        self._notify(ids)

    def on_edges_changed(self, touched_node_ids: list[str]) -> None:
        for n in touched_node_ids:
            self.invalidate(n)

    # ───────────── пересчёт ─────────────
    def evaluate_now(self) -> None:
        self.invalidate_all()
        self.evaluate_pending()

    def evaluate_pending(self) -> None:
        nodes = self._nodes()
        roots = {n for n in self.pending if n in nodes}
        self.pending.clear()
        if not roots:
            return
        edges = self.schema.edges

        # 1. Подграф: корни + все нижестоящие
        touched = self._descendants(roots)
        # Предки, у которых нет свежих значений (очистка, восстановление из файла), тоже считаем —
        # иначе узел получил бы None вместо настоящего входа и «соврал».
        changed = True
        while changed:
            changed = False
            for e in edges:
                if e.to_node in touched and e.from_node not in touched and e.from_node in nodes:
                    st = self.get_state(e.from_node)
                    if st.dirty or st.restored or (st.outputs is None and st.error is None):
                        touched.add(e.from_node)
                        changed = True

        # 2. Топосорт подграфа (Кан)
        ordered_ids = [n.id for n in self.schema.nodes if n.id in touched]
        order, cyclic = topo_sort(ordered_ids, edges)

        # 3. Узлы цикла — ошибки, не вычисляются
        for n in cyclic:
            st = self.get_state(n)
            st.error, st.outputs, st.display_value = "цикл в схеме", None, None
            st.dirty, st.restored = False, False

        # 4. Вычисление в порядке топосорта
        for n in order:
            self._compute(nodes[n])

        # 5. Уведомляем UI
        self._notify(list(touched))

    def clear_values(self) -> None:
        for n in self.schema.nodes:
            self.state[n.id] = NodeRuntime(outputs=None, error=None, dirty=True)
        self._notify([n.id for n in self.schema.nodes])

    # ───────────── сохранение/восстановление (repr) ─────────────
    def export_repr(self) -> dict:
        out: dict[str, Any] = {}
        for node in self.schema.nodes:
            st = self.state.get(node.id)
            if st is None:
                continue
            if st.outputs is None and st.error is None and st.display_value is None:
                continue
            spec = get_spec(node.type)
            entry: dict[str, Any] = {
                "outputs": {k: self._to_repr(st, v, spec.runnable)
                            for k, v in (st.outputs or {}).items()},
                "error": st.error,
            }
            if st.display_value is not None:
                entry["display"] = self._to_repr(st, st.display_value, True)
            out[node.id] = entry
        return out

    def restore_from_repr(self, runtime_json: dict) -> None:
        ids = self._nodes()
        for node_id, entry in runtime_json.items():
            if node_id not in ids or not isinstance(entry, dict):
                continue
            raw_out = entry.get("outputs")
            err = entry.get("error")
            err = err if isinstance(err, str) else None
            outputs = None
            if isinstance(raw_out, dict) and err is None:
                outputs = {str(k): (None if v == "None" else v) for k, v in raw_out.items()
                           if isinstance(v, str) or v is None}
            disp = entry.get("display")
            self.state[node_id] = NodeRuntime(
                outputs=outputs, error=err, dirty=True,
                display_value=(None if disp in (None, "None") else disp), restored=True)

    # ───────────── внутреннее ─────────────
    def _nodes(self) -> dict[str, Node]:
        return {n.id: n for n in self.schema.nodes}

    def _descendants(self, roots: set[str]) -> set[str]:
        adj: dict[str, list[str]] = {}
        for e in self.schema.edges:
            adj.setdefault(e.from_node, []).append(e.to_node)
        known = set(self._nodes())
        seen: set[str] = set()
        frontier = [r for r in roots if r in known]
        while frontier:
            n = frontier.pop()
            if n in seen:
                continue
            seen.add(n)
            frontier.extend(adj.get(n, ()))
        return seen

    def _collect_inputs(self, node: Node) -> dict[str, Any]:
        spec = get_spec(node.type)
        values: dict[str, Any] = {p.name: None for p in spec.inputs}
        nodes = self._nodes()
        for e in self.schema.edges:
            if e.to_node != node.id or not (0 <= e.to_port < len(spec.inputs)):
                continue
            src = nodes.get(e.from_node)
            if src is None:
                continue
            src_spec = get_spec(src.type)
            if not (0 <= e.from_port < len(src_spec.outputs)):
                continue
            st = self.state.get(e.from_node)
            if st is None or st.error is not None or st.outputs is None:
                continue                                  # ошибка/нет значения → вход None
            values[spec.inputs[e.to_port].name] = st.outputs.get(src_spec.outputs[e.from_port].name)
        return values

    def _compute(self, node: Node) -> None:
        spec = get_spec(node.type)
        st = self.get_state(node.id)
        st.dirty, st.restored = False, False
        st.display_value = None
        try:
            inputs = coerce(spec, self._collect_inputs(node))
            if spec.fn is None:                           # дисплей-узел (result)
                st.outputs, st.error = {}, None
                st.display_value = inputs.get("in")
                return
            outs = spec.fn(inputs, node.params)
            st.outputs, st.error = self._check_ports(spec, outs), None
        except FlowError as e:
            st.error, st.outputs = str(e), None
        except Exception as e:  # noqa: BLE001 — узел не должен ронять приложение
            st.error, st.outputs = f"{type(e).__name__}: {e}", None

    @staticmethod
    def _check_ports(spec, outs: Any) -> dict[str, Any]:
        outs = dict(outs) if isinstance(outs, dict) else {}
        for p in spec.outputs:
            if p.name not in outs:
                log.warning("fn узла %s не вернула порт %s", spec.type, p.name)
                outs[p.name] = None
        return outs

    @staticmethod
    def _to_repr(st: NodeRuntime, value: Any, runnable: bool) -> str | None:
        if value is None:
            return None
        if isinstance(value, str) and (st.restored or not runnable):
            return value[:MAX_REPR]
        if hasattr(value, "dtype") and getattr(value, "ndim", 1) == 0:
            value = value.item()                      # np.float64(2.0) → 2.0
        return repr(value)[:MAX_REPR]

    def _notify(self, ids: list[str]) -> None:
        for cb in list(self._listeners):
            try:
                cb(ids)
            except Exception:  # noqa: BLE001
                log.exception("ошибка в слушателе flow_service")
