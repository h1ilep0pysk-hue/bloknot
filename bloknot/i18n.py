"""Interface language. Source strings are English; RU is a lookup table.

t("Text") returns the Russian translation when the language is "ru", otherwise the text itself.
Unknown keys fall back to the key, so saved Russian titles keep displaying.
"""
from __future__ import annotations

import json
from typing import Any

from .paths import data_dir

LANGUAGES = {"en": "English", "ru": "Русский"}
DEFAULT_LANGUAGE = "en"
_current = DEFAULT_LANGUAGE

_RU: dict[str, str] = {
    # ── главное окно и меню ──
    "Idea": "Идея", "Schema": "Схема", "Saved": "Сохранено",
    "Database unavailable — changes are not saved": "База данных недоступна — не сохраняется",
    "project": "проект", "Delete project": "Удаление проекта",
    'Delete project "{name}"?': 'Удалить проект "{name}"?',
    "No project is open": "Нет открытого проекта",
    "Export Markdown": "Экспорт Markdown", "Could not save the file": "Не удалось сохранить файл",
    "Exported": "Экспортировано", "Export for AI": "Экспорт для ИИ",
    "Exported for AI": "Экспортировано для ИИ",
    "Settings": "Настройки", "Language": "Язык",
    "Restart Bloknot to apply the language": "Перезапустите Bloknot, чтобы применить язык",
    # ── вкладка «Идея» и сайдбар ──
    "Create your first project": "Создайте первый проект", "+ New project": "+ Новый проект",
    "Project name": "Название проекта", "Short idea": "Краткая идея",
    "One or two sentences: what the app is and why": "Одно-два предложения: что за приложение и зачем",
    "Detailed description": "Подробное описание",
    "How it works, what architecture, where data comes from…":
        "Как это работает, какая архитектура, что откуда берёт…",
    "Projects": "Проекты", "Delete": "Удалить",
    # ── вкладка «Схема» ──
    "Recalculate all": "Пересчитать всё", "Auto": "Авто", "Clear values": "Очистить значения",
    "Drag a block · output → input to link · Ctrl+wheel zoom · Delete to remove":
        "Перетащите блок · выход → вход — связь · Ctrl+колесо — зум · Delete — удалить",
    "Drag onto the canvas or double-click": "Перетащите на канву или дважды щёлкните",
    # ── панель параметров ──
    "Select a block": "Выберите блок", "Node name": "Название узла",
    "Duplicate": "Дублировать", "Syntax": "Синтаксис", "How to use": "Как использовать",
    "Link example": "Пример связи",
    # ── категории палитры ──
    "Data & code": "Данные и код", "Sources": "Источники", "Extraction": "Извлечение",
    "Logic": "Логика", "Actions": "Действия", "Custom": "Свои", "Result": "Итог",
    # ── названия блоков ──
    "Number": "Число", "Text": "Текст", "List": "Список", "Operator": "Оператор",
    "Python expression": "Python-выражение", "Element [i]": "Элемент [i]", "Branch": "Ветка",
    "Merge": "Объединить", "Matrix": "Матрица", "Determinant": "Определитель",
    "Inverse matrix": "Обратная матрица", "Site / URL": "Сайт / URL",
    "Text by hand": "Текст вручную", "File": "Файл", "HTML parser": "Парс HTML",
    "Extract data": "Извлечь данные", "Clean up": "Очистить", "For each": "Для каждого",
    "Use in my project": "Использовать у себя", "Export report": "Экспорт отчёта",
    "Custom block": "Свой блок", "Unknown node": "Неизвестный узел",
    # ── подписи параметров ──
    "Value": "Значение", "Items": "Элементы", "Operation": "Операция", "Expression": "Выражение",
    "Index": "Индекс", "Condition": "Условие", "Separator": "Разделитель", "Rows": "Строки",
    "URL": "URL", "CSS selector": "CSS-селектор", "Attribute": "Атрибут", "Mode": "Режим",
    "Pattern": "Шаблон", "What to remove": "Что убрать", "Step": "Шаг", "Where": "Куда",
    "Name": "Имя", "Format": "Формат", "Path": "Путь", "Block description": "Описание блока",
    # ── подсказки ──
    "Block description placeholder": "Что делает этот блок",
    "Untitled": "Без названия",
}

_STRINGS_EN: dict[str, str] = {}   # reserved for future en-only overrides


def t(text: str, **kwargs: Any) -> str:
    if _current == "ru":
        text = _RU.get(text, text)
    return text.format(**kwargs) if kwargs else text


def get_language() -> str:
    return _current


def set_language(code: str) -> None:
    global _current
    _current = code if code in LANGUAGES else DEFAULT_LANGUAGE


def _settings_path():
    return data_dir() / "settings.json"


def init_from_settings() -> None:
    """Вызывается один раз при запуске, до создания окна: применяет язык из settings.json."""
    set_language(load_language())


def load_language() -> str:
    try:
        return json.loads(_settings_path().read_text(encoding="utf-8")).get("language", DEFAULT_LANGUAGE)
    except (OSError, ValueError, AttributeError):
        return DEFAULT_LANGUAGE


def save_language(code: str) -> None:
    path = _settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"language": code}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
