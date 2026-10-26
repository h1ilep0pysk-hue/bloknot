# SPEC_FLOW — исполняющий движок dataflow

> Обязательная спецификация. Отвечает на вопросы: когда пересчитывается граф, как именно, как обрабатываются ошибки и циклы, как работает песочница eval и как восстанавливаются значения после перезапуска.

## 1. Место и роли

- Класс: `services/flow_service.py` (`FlowService`). Не импортирует PySide6; общается с UI колбэками.
- Хранит: `dict[node_id → NodeRuntime]` и ссылку на текущую схему.
- Не хранит живые значения в документе: `SchemaGraph` — структура, runtime — живой слой.

## 2. Кому что доступно

| Потребитель | Как пользуется |
|---|---|
| UI (канва) | читает `get_state(node_id)` для отрисовки чипов/полос; подписан `register_listener(cb)` |
| project_service | вызывает `invalidate(node_id)` при изменении параметра |
| schema_service/UI | вызывает `invalidate_all()` при загрузке, `on_edges_changed(...)` при переподключении |
| Кнопки тулбара | `evaluate_now()`, `clear_values()`, `set_live(bool)` |

## 3. API (сигнатуры)

```python
class FlowService:
    def set_schema(self, schema: SchemaGraph) -> None
    def register_listener(self, cb: Callable[[list[str]], None]) -> None
    def set_live(self, on: bool) -> None

    def invalidate(self, node_id: str) -> None          # узел изменился
    def invalidate_all(self) -> None                    # пометить всё устаревшим
    def on_edges_changed(self, touched_node_ids: list[str]) -> None
    def evaluate_pending(self) -> None                  # вызв. по таймеру 200 мс
    def evaluate_now(self) -> None                      # кнопка «▶» — всё немедленно
    def clear_values(self) -> None                      # «Очистить значения»
    def restore_from_repr(self, runtime_json: dict) -> None
    def export_repr(self) -> dict                       # для записи в schema_json
    def get_state(self, node_id: str) -> NodeRuntime
```

## 4. Таймеры (кто держит)

- UI держит **один** `QTimer` (singleShot, 200 мс) для пересчёта, и **один** (500 мс) для сохранения.
- Движок только накапливает `pending: set[node_id]` в `invalidate*()`; UI по таймеру зовёт `evaluate_pending()`.
- Почему так: движок остаётся Qt-независимым (инвариант 9), а таймер — деталь UI.

## 5. Триггеры пересчёта

| Источник события | invalidate кого |
|---|---|
| Изменён параметр узла (inline/панель) | этот узел |
| Создана связь | узел-приёмник |
| Удалена связь | узел-приёмник и узел-источник |
| Удалён узел | все узлы, которые получали значение от удалённого (их входы станут None) |
| Переименование/перемещение узла | НЕ пересчёт (не влияет на данные) |
| Загрузка проекта | все узлы |
| Кнопка «▶ Пересчитать всё» | все узлы |

## 6. Алгоритм `evaluate_pending()` (псевдокод целиком)

```python
def evaluate_pending(self):
    if not self.pending: return
    roots = self.pending; self.pending.clear()

    # 1. Собрать подграф: корни + все нижестоящие (по направлению связей)
    touched = set()
    frontier = list(roots)
    while frontier:
        n = frontier.pop()
        if n in touched: continue
        touched.add(n)
        frontier += [e.to_node for e in self.edges if e.from_node == n]

    # 2. Топосорт подграфа (алгоритм Кана)
    order, cyclic = topo_sort(subgraph(touched, self.edges))

    # 3. Узлы цикла — ошибки, не вычисляются
    for n in cyclic:
        self.state[n].error = "цикл в схеме"
        self.state[n].outputs = None

    # 4. Вычисление в порядке топосорта
    for n in order:
        node = self.nodes[n]; spec = registry[node.type]
        try:
            inputs = self._collect_inputs(node)      # None если связи нет
            inputs = coerce(spec, inputs)            # правила SPEC_CORE п. 4
            if spec.fn is None:
                # дисплей-узлы (result): значение берётся с входа «in»
                self.state[n].outputs = {}
                self.state[n].error = None
                self.state[n].display_value = inputs.get("in")
                continue
            outs = spec.fn(inputs, node.params)      # может raise FlowError
            check_all_ports_present(spec, outs)      # контракт fn
            self.state[n].outputs = outs
            self.state[n].error = None
        except FlowError as e:
            self.state[n].error = str(e)
            self.state[n].outputs = None

    # 5. Уведомляем UI только изменившиеся узлы
    self._notify(list(touched))
```

**Пояснение ключевых мест:**

- *Подграф, не весь граф*: изменение одного параметра не должно пересчитывать сотню не связанных с ним узлов — иначе Live-режим будет «весь граф мелькает».
- *Топосорт (Кан)*: считаем узлы в порядке зависимости — входы уже готовы к моменту вычисления узла. Алгоритм простой: считаем входящие степени, нулевые — в очередь, снимаем их связи; что осталось — цикл.
- *Ошибки вниз*: сломанный узел передаёт «ошибка» потомкам (их входы = None), поэтому цепочка не «врёт» частично.
- *Дисплей-узлы*: `result` без выходов — движок кладёт значение входа в `display_value`, UI рисует чек.
- *Контракт fn*: если `fn` вернула словарь без какого-то выходного порта — это нарушение спецификации, движок добирает `None` и логирует предупреждение (не падает).

## 7. Live-режим и «устаревшие» значения

- `set_live(True)` (по умолчанию): каждое `invalidate` приводит к пересчёту по таймеру 200 мс.
- `set_live(False)`: `pending` копится, но пересчёт — только по кнопке «▶ Пересчитать всё» (`evaluate_now()` = `invalidate_all()` + немедленный `evaluate_pending()`).
- Пока значения устарели (`runtime.dirty=True`), UI рисует в узле приглушённую пометку «устарело» (SPEC_UI, п. 5.5) — так у пользователя нет иллюзии свежих цифр.

## 8. Циклы

- При попытке соединения: `validation.can_connect` проверяет достижимость (BFS) от приёмника к источнику; цикл — отказ, тост «цикл в схеме» (SPEC_CORE, п. 10). Такой связи в графе нет вовсе.
- Если цикл всё же образовался при загрузке файла (ручные правки JSON) — алгоритм Кана сам найдёт «застрявшие» узлы; они получают ошибку «цикл в схеме» и не вычисляются, граф остаётся редактируемым.

## 9. Песочница узла `eval`

```python
SAFE_BUILTINS = {abs, min, max, sum, len, round, sorted,
                 list, tuple, dict, set, str, int, float,
                 bool, zip, map, filter, range, enumerate,
                 any, all, reversed, slice}   # множество функций

def run_eval(inputs, params):
    expr = str(params.get("expr") or "").strip()
    if not expr: return {"out": None}
    ns = {"in0": inputs.get("in0"), "in1": inputs.get("in1")}
    try:
        value = eval(expr, {"__builtins__": SAFE_BUILTINS}, ns)
    except SyntaxError as e:
        raise FlowError(f"синтаксис: {e.msg}")
    except Exception as e:
        raise FlowError(f"{type(e).__name__}: {e}")
    return {"out": value}
```

- **Почему так**: `import` внутри `eval` невозможен (builtins урезаны) — пользовательский код не может открыть файл, уйти в сеть или получить доступ к системе в обход песочницы; выражение ограничено чистыми вычислениями над `in0/in1`.
- Ограничение (сознательное, v1): «вечный цикл» внутри выражения невозможен (eval — только выражения, без `while`), но `2**гигант` замедлит исполнение; защиты от времени исполнения нет — осознанный компромисс: пользователь пишет код для себя. Потоковое исполнение — фаза 2.
- Код из узла **никогда** не сохраняется как объект и не исполняется при загрузке — только в момент пересчёта.

## 10. Восстановление после перезапуска

- `restore_from_repr(runtime_json)`: для каждого узла из JSON — `NodeRuntime`, где `outputs[порт]` — **строка-репрезентация** (не объект!), `dirty=True`, пометка «восстановлено».
- UI показывает такие чипы приглушённо (SPEC_UI). Первый же пересчёт заменяет репрезентации настоящими значениями, и чипы становятся «живыми» (акцентный цвет).
- Зачем: не хранить живые значения в файле, но дать пользователю увидеть «каково было состояние в прошлый раз» без усилий.

## 11. Опциональный numpy

- Проверка: `importlib.util.find_spec("numpy")` (один раз при старте движка, результат кэшируется).
- Нет numpy: матричные блоки (`matrix`, `determinant`, `inverse`) существуют, но их `fn` при вызове возбуждает `FlowError("установи numpy: pip install numpy")`. Полоса узла — DANGER, текст ошибки в тултипе и панели. Крашов нет.
- Есть numpy: `matrix` возвращает `np.ndarray` (в JSON уйдёт repr через `repr(array)`; приведение matrix-порта принимает и list, и ndarray).

## 12. Производительность и ограничения

- Пересчёт — подграф от затронутых корней; без кэшей значений. Почему без кэшей: сравнение произвольных объектов ненадёжно (numpy-массивы, float NaN), а объём — мал (сотни узлов × миллисекунды) — простота важнее микрооптимизации.
- Всё синхронно и однопоточно; debounce гарантирует, что при скролле спина пересчитывается один раз после паузы, а не на каждый кадр.
- Если пользователь соберёт «общемировой» граф на 500 узлов и нажмёт «▶» — один проход топосорта и вычислений; это доли секунды для фильтрованных/числовых операций v1.

## 13. Класс ошибок

```python
class FlowError(Exception):
    """Ошибка вычисления узла; текст — человекочитаемый, на русском."""
```

| Ситуация | Текст ошибки |
|---|---|
| `math` деление на 0 | «деление на ноль» |
| нечисловой вход в `number`-порт | «вход <имя>: не число» |
| `get_index` вне диапазона | «нет элемента [<i>]» |
| `eval` синтаксис | «синтаксис: <детали>» |
| `eval` runtime исключение | «<ТипИсключения>: <msg>» |
| `matrix` не парсится | «матрица: строки через ';', числа через пробел» |
| numpy недоступен | «установи numpy: pip install numpy» |
| цикл | «цикл в схеме» |

Всё это — состояния узлов, а не диалоги и не крахи: приложение продолжает жить (инвариант 4).
