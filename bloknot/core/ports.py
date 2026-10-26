"""Порты и приведение типов (SPEC_CORE п. 4). Без Qt."""
from __future__ import annotations

import numbers
from dataclasses import dataclass
from typing import Any, Literal

PortType = Literal["any", "number", "text", "list", "matrix"]


class FlowError(Exception):
    """Ошибка вычисления узла; текст — человекочитаемый, на русском."""


@dataclass
class PortSpec:
    name: str                      # "a", "b", "out", "yes", "no", ...
    type: PortType = "any"
    label: str = ""                # подпись рядом с портом; пусто = name

    @property
    def caption(self) -> str:
        return self.label or self.name


class _Bad(Exception):
    pass


def _is_num(x: Any) -> bool:
    return isinstance(x, numbers.Number)


def _to_number(v: Any) -> Any:
    if isinstance(v, bool):
        return int(v)
    if _is_num(v):
        return v
    if isinstance(v, str):
        try:
            return float(v.strip().replace(",", "."))
        except ValueError:
            raise _Bad("не число") from None
    if hasattr(v, "tolist") and not isinstance(v, (list, tuple)):
        v = v.tolist()
        if _is_num(v):
            return v
    if isinstance(v, (list, tuple)) and len(v) == 1:
        return _to_number(v[0])
    raise _Bad("не число")


def _to_text(v: Any) -> str:
    return v if isinstance(v, str) else str(v)


def _to_list(v: Any) -> list:
    if isinstance(v, list):
        return v
    if isinstance(v, tuple):
        return list(v)
    if hasattr(v, "tolist"):
        r = v.tolist()
        return r if isinstance(r, list) else [r]
    return [v]


def _to_matrix(v: Any) -> Any:
    if hasattr(v, "ndim") and hasattr(v, "reshape"):          # numpy-массив
        if v.ndim == 2:
            return v
        if v.ndim == 1:
            return v.reshape(1, -1)
        raise _Bad("не матрица")
    if isinstance(v, (list, tuple)) and v:
        if all(_is_num(x) for x in v):
            return [list(v)]
        if all(isinstance(r, (list, tuple)) and r and all(_is_num(x) for x in r) for r in v):
            return [list(r) for r in v]
    raise _Bad("не матрица")


def coerce_value(port_type: str, value: Any) -> Any:
    """Приводит значение к типу порта. None проходит без ошибок."""
    if value is None or port_type == "any":
        return value
    if port_type == "number":
        return _to_number(value)
    if port_type == "text":
        return _to_text(value)
    if port_type == "list":
        return _to_list(value)
    if port_type == "matrix":
        return _to_matrix(value)
    return value


def coerce(spec: Any, inputs: dict[str, Any]) -> dict[str, Any]:
    """Приведение всех входов узла до вызова fn. Ошибка — ошибка узла-приёмника."""
    result: dict[str, Any] = {}
    for port in spec.inputs:
        try:
            result[port.name] = coerce_value(port.type, inputs.get(port.name))
        except _Bad as e:
            raise FlowError(f"вход {port.name}: {e}") from None
    return result


def to_plain(value: Any) -> Any:
    """numpy-скаляры и 0-мерные значения → обычные python-числа; массивы → вложенные списки.
    Нужно только для отображения: np.float64(2.0) показываем как 2.0."""
    if hasattr(value, "dtype") and hasattr(value, "tolist"):
        return value.tolist()
    return value
