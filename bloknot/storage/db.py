"""Подключение к SQLite (SPEC_STORAGE п. 1–2). Единственное место, где открывается соединение."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_SCHEMA_JSON = '{"version": 2, "nodes": [], "edges": []}'

_CREATE = f"""
CREATE TABLE IF NOT EXISTS projects (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    idea_summary TEXT NOT NULL DEFAULT '',
    description  TEXT NOT NULL DEFAULT '',
    schema_json  TEXT NOT NULL DEFAULT '{DEFAULT_SCHEMA_JSON}',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
)
"""


def default_db_path() -> Path:
    """data/bloknot.sqlite3 рядом с main.py (или рядом с exe в собранной версии)."""
    from ..paths import data_dir
    return data_dir() / "bloknot.sqlite3"


def _prepare(conn: sqlite3.Connection, wal: bool) -> sqlite3.Connection:
    conn.row_factory = sqlite3.Row
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(_CREATE)
    conn.commit()
    return conn


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return _prepare(sqlite3.connect(str(path)), wal=True)


def connect_memory() -> sqlite3.Connection:
    """Запасной режим, когда файл базы недоступен: работаем в памяти."""
    return _prepare(sqlite3.connect(":memory:"), wal=False)
