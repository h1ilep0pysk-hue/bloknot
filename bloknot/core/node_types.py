"""Реестр всех блоков (SPEC_CORE п. 5–9). Без Qt."""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from typing import Any, Callable

from .ports import FlowError, PortSpec

_NUMPY_HINT = "установи numpy: pip install numpy"


def numpy_module():
    """Опциональный numpy (SPEC_FLOW п. 11): None, если не установлен."""
    if not getattr(numpy_module, "_checked", False):
        numpy_module._available = importlib.util.find_spec("numpy") is not None
        numpy_module._checked = True
    if not numpy_module._available:
        return None
    import numpy
    return numpy


# ───────────── параметры и спецификация блока (SPEC_CORE п. 5–6) ─────────────
@dataclass
class ParamSpec:
    key: str
    label: str
    widget: str                     # "spin" | "line" | "text" | "combo" | "code"
    default: Any
    inline: bool = False
    options: list | None = None
    min: float = 0
    max: float = 100
    step: float = 1
    placeholder: str = ""
    rows: int = 2


@dataclass
class NodeSpec:
    type: str
    title: str
    category: str
    inputs: list[PortSpec] = field(default_factory=list)
    outputs: list[PortSpec] = field(default_factory=list)
    params: dict[str, ParamSpec] = field(default_factory=dict)
    runnable: bool = False
    fn: Callable | None = None
    body_port: str | None = None
    opt_deps: list[str] = field(default_factory=list)


def default_params(spec: NodeSpec) -> dict[str, Any]:
    return {key: ps.default for key, ps in spec.params.items()}


# ───────────── песочница eval (SPEC_FLOW п. 9) ─────────────
SAFE_BUILTINS = {abs, min, max, sum, len, round, sorted,
                 list, tuple, dict, set, str, int, float,
                 bool, zip, map, filter, range, enumerate,
                 any, all, reversed, slice}


def run_eval(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    expr = str(params.get("expr") or "").strip()
    if not expr:
        return {"out": None}
    if "__" in expr:                        # dunder-обход песочницы запрещён
        raise FlowError("недопустимо: «__» в выражении")
    ns = {"in0": inputs.get("in0"), "in1": inputs.get("in1")}
    builtins = {b.__name__: b for b in SAFE_BUILTINS}
    try:
        value = eval(expr, {"__builtins__": builtins}, ns)  # noqa: S307
    except SyntaxError as e:
        raise FlowError(f"синтаксис: {e.msg}") from None
    except Exception as e:  # noqa: BLE001
        raise FlowError(f"{type(e).__name__}: {e}") from None
    return {"out": value}


# ───────────── fn исполняемых блоков (SPEC_CORE п. 7) ─────────────
def _np():
    np = numpy_module()
    if np is None:
        raise FlowError(_NUMPY_HINT)
    return np


def _parse_list_items(text: str) -> list:
    out = []
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            try:
                out.append(float(part))
            except ValueError:
                out.append(part)
    return out


def _fn_number(inputs, params):
    return {"out": params.get("value")}


def _fn_text(inputs, params):
    return {"out": params.get("value")}


def _fn_list(inputs, params):
    return {"out": _parse_list_items(params.get("items") or "")}


def _fn_math(inputs, params):
    a, b = inputs.get("a"), inputs.get("b")
    op = params.get("op")
    if a is None or b is None:
        return {"out": None}
    if op == "+":
        out = a + b
    elif op == "-":
        out = a - b
    elif op == "*":
        out = a * b
    elif op == "/":
        if b == 0:
            raise FlowError("деление на ноль")
        out = a / b
    elif op == "**":
        out = a ** b
    else:
        raise FlowError(f"неизвестная операция: {op}")
    return {"out": out}


def _fn_get_index(inputs, params):
    src, i = inputs.get("src"), params.get("i")
    if src is None:
        return {"out": None}
    try:
        if isinstance(src, dict):
            return {"out": src[int(i)]}
        return {"out": src[int(i)]}
    except (IndexError, KeyError, TypeError):
        raise FlowError(f"нет элемента [{i}]") from None


def _fn_branch(inputs, params):
    v = inputs.get("in")
    cond, value = params.get("cond"), params.get("value") or ""
    if cond == "больше чем":
        try:
            ok = float(str(v).replace(",", ".")) > float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            raise FlowError("сравнение: не число") from None
    elif cond == "равно":
        ok = str(v) == str(value)
    else:                                       # «содержит»
        ok = str(value) in str(v)
    return {"yes": v if ok else None, "no": None if ok else v}


def _fn_merge(inputs, params):
    a, b = inputs.get("a"), inputs.get("b")
    sep = str(params.get("sep") or "")
    parts = [str(x) for x in (a, b) if x is not None]
    return {"out": sep.join(parts)}


def _parse_matrix(text: str) -> list[list[float]]:
    rows = []
    for line in str(text).split(";"):
        line = line.strip()
        if not line:
            continue
        row = []
        for token in line.replace(",", " ").split():
            try:
                row.append(float(token))
            except ValueError:
                raise FlowError("матрица: строки через ';', числа через пробел") from None
        if row:
            rows.append(row)
    if not rows:
        raise FlowError("матрица: строки через ';', числа через пробел")
    return rows


def _fn_matrix(inputs, params):
    rows = _parse_matrix(params.get("rows") or "")
    np = numpy_module()
    return {"out": np.array(rows) if np is not None else rows}


def _fn_determinant(inputs, params):
    np = _np()
    m = inputs.get("m")
    if m is None:
        return {"out": None}
    return {"out": float(np.linalg.det(m))}


def _fn_inverse(inputs, params):
    np = _np()
    m = inputs.get("m")
    if m is None:
        return {"out": None}
    return {"out": np.linalg.inv(m)}


# ───────────── заглушка проектных блоков (SPEC_CORE п. 8) ─────────────
def _make_project_fn(spec: NodeSpec) -> Callable:
    def fn(inputs, params):
        parts = []
        for ps in spec.params.values():
            val = params.get(ps.key, ps.default)
            if val not in (None, ""):
                parts.append(f"{ps.label}: {' '.join(str(val).split())}")
        return {"out": f"{spec.title}: {'; '.join(parts)}" if parts else spec.title}
    return fn


# ───────────── реестр ─────────────
def _spec(**kw) -> NodeSpec:
    return NodeSpec(**kw)


def _p(name: str, type_: str = "any", label: str = "") -> PortSpec:
    return PortSpec(name=name, type=type_, label=label)          # type: ignore[arg-type]


_REGISTRY: dict[str, NodeSpec] = {}


def _register(spec: NodeSpec) -> None:
    if spec.runnable and spec.fn is None and spec.outputs:
        raise ValueError(f"блок {spec.type} без fn")   # дисплей-узлы без выходов fn не нужен
    _REGISTRY[spec.type] = spec


# «Данные и код» (исполняемые)
_register(_spec(type="number", title="Number", category="Data & code", runnable=True,
                outputs=[_p("out", "number")], fn=_fn_number, body_port="out",
                params={"value": ParamSpec("value", "Value", "spin", 2.0, inline=True,
                                           min=-1e12, max=1e12, step=1)}))
_register(_spec(type="text", title="Text", category="Data & code", runnable=True,
                outputs=[_p("out", "text")], fn=_fn_text, body_port="out",
                params={"value": ParamSpec("value", "Value", "line", "", inline=True)}))
_register(_spec(type="list", title="List", category="Data & code", runnable=True,
                outputs=[_p("out", "list")], fn=_fn_list, body_port="out",
                params={"items": ParamSpec("items", "Items", "line", "", inline=True,
                                           placeholder="1, два, 3.5")}))
_register(_spec(type="math", title="Operator", category="Data & code", runnable=True,
                inputs=[_p("a", "number"), _p("b", "number")],
                outputs=[_p("out", "number")], fn=_fn_math, body_port="out",
                params={"op": ParamSpec("op", "Operation", "combo", "**", inline=True,
                                        options=["+", "-", "*", "/", "**"])}))
_register(_spec(type="eval", title="Python expression", category="Data & code", runnable=True,
                inputs=[_p("in0"), _p("in1")], outputs=[_p("out")],
                fn=run_eval, body_port="out",
                params={"expr": ParamSpec("expr", "Expression", "code", "", inline=True, rows=2,
                                          placeholder="in0[0][0]")}))
_register(_spec(type="get_index", title="Element [i]", category="Data & code", runnable=True,
                inputs=[_p("src"), _p("i", "number")], outputs=[_p("out")],
                fn=_fn_get_index, body_port="out",
                params={"i": ParamSpec("i", "Index", "spin", 0.0, inline=True,
                                       min=-1e9, max=1e9, step=1)}))
_register(_spec(type="branch", title="Branch", category="Data & code", runnable=True,
                inputs=[_p("in")], outputs=[_p("yes", label="да"), _p("no", label="нет")],
                fn=_fn_branch, body_port="*",
                params={"cond": ParamSpec("cond", "Condition", "combo", "содержит", inline=True,
                                          options=["содержит", "больше чем", "равно"]),
                        "value": ParamSpec("value", "Value", "line", "", inline=True)}))
_register(_spec(type="merge", title="Merge", category="Data & code", runnable=True,
                inputs=[_p("a"), _p("b")], outputs=[_p("out", "text")],
                fn=_fn_merge, body_port="out",
                params={"sep": ParamSpec("sep", "Separator", "line", " ", inline=True)}))
_register(_spec(type="matrix", title="Matrix", category="Data & code", runnable=True,
                outputs=[_p("out", "matrix")], fn=_fn_matrix, body_port="out",
                params={"rows": ParamSpec("rows", "Rows", "text", "", inline=True, rows=3,
                                          placeholder="1 2 3; 4 5 6")}))
_register(_spec(type="determinant", title="Determinant", category="Data & code", runnable=True,
                inputs=[_p("m", "matrix")], outputs=[_p("out", "number")],
                fn=_fn_determinant, body_port="out", opt_deps=["numpy"]))
_register(_spec(type="inverse", title="Inverse matrix", category="Data & code", runnable=True,
                inputs=[_p("m", "matrix")], outputs=[_p("out", "matrix")],
                fn=_fn_inverse, body_port="out", opt_deps=["numpy"]))
# «Итог»
def _fn_result(inputs, params):
    # пропускает значение дальше; если выход не соединён — это окончательный ответ
    return {"out": inputs.get("in")}


_register(_spec(type="result", title="Result", category="Result", runnable=True,
                inputs=[_p("in")], outputs=[_p("out")], fn=_fn_result, body_port="out"))

# Проектные блоки (runnable=False)
for _ps in (
    _spec(type="site_url", title="Site / URL", category="Sources",
          outputs=[_p("out")],
          params={"url": ParamSpec("url", "URL", "line", "", placeholder="https://...")}),
    _spec(type="manual_text", title="Text by hand", category="Sources",
          outputs=[_p("out")],
          params={"text": ParamSpec("text", "Text", "text", "", rows=3)}),
    _spec(type="file", title="File", category="Sources",
          outputs=[_p("out")],
          params={"path": ParamSpec("path", "Path", "line", ""),
                  "fmt": ParamSpec("fmt", "Format", "combo", "html",
                                   options=["html", "json", "csv", "текст"])}),
    _spec(type="parse_html", title="HTML parser", category="Extraction",
          inputs=[_p("in")], outputs=[_p("out")],
          params={"selector": ParamSpec("selector", "CSS selector", "line", ""),
                  "attr": ParamSpec("attr", "Attribute", "combo", "текст",
                                    options=["текст", "href", "src"])}),
    _spec(type="extract", title="Extract data", category="Extraction",
          inputs=[_p("in")], outputs=[_p("out")],
          params={"mode": ParamSpec("mode", "Mode", "combo", "regex",
                                    options=["regex", "json-ключ", "числа", "ссылки"]),
                  "pattern": ParamSpec("pattern", "Pattern", "line", "")}),
    _spec(type="clean", title="Clean up", category="Extraction",
          inputs=[_p("in")], outputs=[_p("out")],
          params={"what": ParamSpec("what", "What to remove", "combo", "пробелы по краям",
                                    options=["пробелы по краям", "дубли", "пустые"])}),
    _spec(type="loop", title="For each", category="Logic",
          inputs=[_p("in")], outputs=[_p("out")],
          params={"step": ParamSpec("step", "Step", "line", "")}),
    _spec(type="act_use", title="Use in my project", category="Actions",
          inputs=[_p("in")], outputs=[],
          params={"where": ParamSpec("where", "Where", "combo", "в описание",
                                     options=["в описание", "в заметку", "в переменную"]),
                  "name": ParamSpec("name", "Name", "line", "")}),
    _spec(type="act_export", title="Export report", category="Actions",
          inputs=[_p("in")], outputs=[],
          params={"fmt": ParamSpec("fmt", "Format", "combo", "markdown",
                                   options=["markdown", "json"])}),
):
    _ps.runnable = False
    _ps.fn = _make_project_fn(_ps)
    if _ps.type in ("act_use", "act_export"):
        _ps.body_port = None
    else:
        _ps.body_port = "out"
    _register(_ps)

# Свой блок: визуальный компонент архитектуры (название и описание задаёт пользователь, значений не считает)
_custom = _spec(type="custom", title="Custom block", category="Custom", runnable=False,
                inputs=[_p("in")], outputs=[_p("out")],
                params={"note": ParamSpec("note", "Block description", "text", "", rows=3,
                                          placeholder="Что делает этот блок")})
_custom.fn = _make_project_fn(_custom)
_custom.body_port = "out"
_register(_custom)

# unknown — защита от битых схем (SPEC_CORE п. 9)
_register(_spec(type="unknown", title="Unknown node", category="Result", runnable=False))

# Визуальная схема: у каждого блока (кроме unknown) есть вход и выход, даже если не считается.
# Порты дописываются в КОНЕЦ списка, поэтому индексы старых связей не сдвигаются.
for _spec_ in _REGISTRY.values():
    if _spec_.type == "unknown":
        continue
    if not _spec_.inputs:
        _spec_.inputs.append(_p("in"))
    if not _spec_.outputs:
        _spec_.outputs.append(_p("out"))

# порядок в палитре (SPEC_UI п. 5.2)
_CATEGORY_ORDER = ["Data & code", "Sources", "Extraction", "Logic", "Actions", "Custom", "Result"]


def get_spec(type_: str) -> NodeSpec:
    return _REGISTRY.get(type_) or _REGISTRY["unknown"]


def is_known(type_: str) -> bool:
    return type_ in _REGISTRY


def all_specs() -> list[NodeSpec]:
    return list(_REGISTRY.values())


def palette_groups() -> list[tuple[str, list[NodeSpec]]]:
    groups: list[tuple[str, list[NodeSpec]]] = []
    for cat in _CATEGORY_ORDER:
        specs = [s for s in _REGISTRY.values() if s.category == cat and s.type != "unknown"]
        if specs:
            groups.append((cat, specs))
    return groups


# ───────────── синтаксис и пример использования (подсказка в панели параметров) ─────────────
# type → (синтаксис, пример)
SYNTAX: dict[str, tuple[str, str]] = {
    "number": ("число → out:number",
               "Значение = 2 → out: 2.0. Источник константы: подключите к Оператору или eval."),
    "text": ("текст → out:text",
             "Значение = «привет» → out: привет. Далее — в Объединить или Результат."),
    "list": ("«a, b, c» (через запятую) → out:list",
             "Элементы = 1, два, 3.5 → [1, 'два', 3.5]. Числа распознаются автоматически."),
    "math": ("a:number ⟮op⟯ b:number → out:number, op ∈ {+ − * / **}",
             "a = Число 2, b = Число 3, op = ** → out: 8.0. При / и b=0 — «деление на ноль»."),
    "eval": ("eval(expr, in0, in1) → out:any",
             "expr = in0[0][0] — первый элемент первого вложенного списка входа in0."),
    "get_index": ("src:any[i:number] → out:any",
                  "src = [10, 20, 30], i = 1 → out: 20. Для dict i — ключ."),
    "branch": ("in:any → (yes|no):any по cond и value",
               "cond = «содержит», value = 3, in = 3.14 → да: 3.14. Иначе значение идёт в «нет»."),
    "merge": ("str(a) + sep + str(b) → out:text",
              "a = «итог», b = 2026, sep = «  » → out: «итог 2026». None-части пропускаются."),
    "matrix": ("«1 2; 3 4» (строки через ';') → out:matrix",
               "Строки = 1 2; 3 4 → [[1.0, 2.0], [3.0, 4.0]]. С numpy — ndarray для матричных узлов."),
    "determinant": ("det(M:matrix) → out:number  [numpy]",
                    "M = [[1, 2], [3, 4]] → out: -2.0. Без numpy — подсказка установить."),
    "inverse": ("inv(M:matrix) → out:matrix  [numpy]",
                "M = [[1, 2], [3, 4]] → [[-2.0, 1.0], [1.5, -0.5]]."),
    "result": ("in:any → out:any (чек значения)",
               "Подключите любой выход — значение покажется в чеке; out не соединён = окончательный ответ."),
    "site_url": ("(проектный) url → out: строка-описание шага",
                 "URL = https://example.com → далее Парс HTML. Значение — план, не запрос."),
    "manual_text": ("(проектный) текст → out: строка-описание шага",
                    "Вставьте сюда образец данных, с которым проектируете схему."),
    "file": ("(проектный) path, fmt → out: строка-описание шага",
             "Путь = data/report.csv, Формат = csv — план чтения локального файла."),
    "parse_html": ("(проектный) in → out: строка-описание шага",
                   "Сайт/URL → Парс HTML (селектор .price, атрибут текст) → Извлечь данные."),
    "extract": ("(проектный) in → out: строка-описание шага",
                r"Режим = regex, Шаблон = \d+ — план извлечения чисел из собранного текста."),
    "clean": ("(проектный) in → out: строка-описание шага",
              "Что убрать = «пустые» — шаг очистки списка перед использованием."),
    "loop": ("(проектный) in → out: строка-описание шага",
             "Шаг = «для каждой строки таблицы» — план перебора элементов."),
    "act_use": ("(проектный) in → out: строка-описание шага",
                "Куда = «в описание» — завершающий шаг: результат кладётся в проект."),
    "act_export": ("(проектный) in → out: строка-описание шага",
                   "Формат = markdown — план выгрузки отчёта в файл."),
    "custom": ("(свой) in → out: визуальный блок, значения не считает",
               "Назовите блок, например «ЛОКАЛЬНАЯ ИИ МОДЕЛЬ», и соедините его с другими блоками."),
    "unknown": ("тип узла не распознан",
                "Узел из битой схемы или удалённого блока. Данные не потеряны — удалите вручную."),
}


def block_syntax(type_: str) -> tuple[str, str]:
    return SYNTAX.get(type_, ("", ""))


# ───────────── как использовать и пример связи (панель параметров справа) ─────────────
# type → (как использовать, пример связи). Порты: имя блока.порт
USAGE: dict[str, tuple[str, str]] = {
    "number": ("Константа-число. Задай значение; выход отдаёт число другим блокам.",
               "Число(2).out → Оператор.a;  Число(3).out → Оператор.b  →  Оператор(**).out = 8.0"),
    "text": ("Строка. Удобно для склейки через «Объединить» и для условий в «Ветке».",
             "Текст(«итог»).out → Объединить.a;  Число(2026).out → Объединить.b  →  «итог 2026»"),
    "list": ("Список из строки через запятую. Числа распознаются сами.",
             "Список(10, 20, 30).out → Элемент [i].src;  Число(1).out → Элемент [i].i  →  20"),
    "math": ("Арифметика над двумя числами. Операция выбирается в поле «Операция».",
             "Число(2).out → Оператор.a;  Число(3).out → Оператор.b;  Операция = **  →  8.0"),
    "eval": ("Выражение Python над входами in0 и in1. Разрешены только безопасные функции "
             "(len, sum, sorted…); import и «__» запрещены.",
             "Список(1, 2, 3).out → eval.in0;  выражение: sum(in0)  →  6"),
    "get_index": ("Берёт элемент по индексу i из списка, строки или словаря.",
                  "Список(10, 20, 30).out → Элемент [i].src;  i = 1  →  20"),
    "branch": ("Проверяет вход по условию: значение уходит в «да» или «нет». Невыбранный выход пуст.",
               "Текст(«abc123»).out → Ветка.in;  условие = содержит, значение = 123  →  «да»: abc123"),
    "merge": ("Склеивает два значения в текст через разделитель.",
              "Текст(«итог»).out → Объединить.a;  Число(2026).out → Объединить.b  →  «итог 2026»"),
    "matrix": ("Матрица из текста: строки через «;», числа через пробел. Нужна для определителя и обратной матрицы.",
               "Матрица(«1 2; 3 4»).out → Определитель.m  →  ≈ -2.0"),
    "determinant": ("Определитель квадратной матрицы. Нужен numpy: pip install numpy.",
                    "Матрица(«1 2; 3 4»).out → Определитель.m  →  ≈ -2.0"),
    "inverse": ("Обратная матрица. Нужен numpy.",
                "Матрица(«1 2; 3 4»).out → Обратная матрица.m  →  [[-2, 1], [1.5, -0.5]]"),
    "result": ("Показывает значение в чеке. Выход «out» не соединён — это окончательный ответ. "
               "Соединён — значение передаётся дальше по цепочке.",
               "Оператор.out → Результат.in → 8.0 (итог).   Результат.out → Оператор(+).a — цепочка продолжается"),
    "site_url": ("Адрес страницы. Пока только описывает шаг: страница не загружается.",
                 "Сайт(https://example.com).out → Парс HTML.in"),
    "manual_text": ("Образец текста, с которым проектируешь схему. Пока только описание шага.",
                    "Текст вручную.out → Извлечь данные.in"),
    "file": ("Путь к локальному файлу и формат. Пока только описание шага.",
             "Файл(data/report.csv, csv).out → Извлечь данные.in"),
    "parse_html": ("Описывает, какой элемент страницы взять (CSS-селектор) и что из него брать.",
                   "Сайт.out → Парс HTML(селектор .price, текст).in → Извлечь данные.in"),
    "extract": ("Описывает, как вытащить данные: regex, ключ JSON, числа или ссылки.",
                "Парс HTML.out → Извлечь данные(режим = числа).in → Очистить.in"),
    "clean": ("Описывает очистку: пробелы по краям, дубли, пустые значения.",
              "Извлечь данные.out → Очистить(дубли).in → Использовать у себя.in"),
    "loop": ("Описывает перебор элементов по шагам.",
             "Извлечь данные(ссылки).out → Для каждого(шаг: открыть ссылку).in → Использовать у себя.in"),
    "act_use": ("Конечный шаг: куда положить результат (в описание, заметку, переменную). Выход — для визуальной цепочки.",
                "Очистить.out → Использовать у себя(в описание).in"),
    "act_export": ("Конечный шаг: выгрузка отчёта (markdown или json). Выход — для визуальной цепочки.",
                   "Извлечь данные.out → Экспорт отчёта(markdown).in"),
    "custom": ("Визуальный блок архитектуры. Назови его в поле «Название узла» (например «ЛОКАЛЬНАЯ ИИ МОДЕЛЬ») и опиши в «Описание блока». Ничего не вычисляет.",
               "ЛОКАЛЬНАЯ ИИ МОДЕЛЬ.out → Использовать у себя.in"),
    "unknown": ("Узел из битой схемы или удалённого блока. Данные не потеряны — удалите вручную.",
                "Связи не создаёт"),
}


def block_usage(type_: str) -> tuple[str, str]:
    return USAGE.get(type_, ("", ""))
