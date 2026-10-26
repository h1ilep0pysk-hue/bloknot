"""CRUD проектов (SPEC_STORAGE п. 4). Только SQL, никакой доменной логики."""
from __future__ import annotations

import sqlite3
from typing import Any

from ..core.models import now_iso

_COLUMNS = ("id", "name", "idea_summary", "description", "schema_json", "created_at", "updated_at")

_UPSERT = """
INSERT INTO projects (id, name, idea_summary, description, schema_json, created_at, updated_at)
VALUES (:id, :name, :idea_summary, :description, :schema_json, :created_at, :updated_at)
ON CONFLICT(id) DO UPDATE SET
    name=excluded.name, idea_summary=excluded.idea_summary, description=excluded.description,
    schema_json=excluded.schema_json, updated_at=excluded.updated_at
"""


class ProjectRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def get_all(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM projects ORDER BY created_at ASC, rowid ASC").fetchall()
        return [dict(r) for r in rows]

    def get(self, project_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return dict(row) if row else None

    def create(self, project_id: str, name: str, idea_summary: str, description: str,
               schema_json: str, created_at: str) -> dict[str, Any]:
        row = dict(id=project_id, name=name, idea_summary=idea_summary, description=description,
                   schema_json=schema_json, created_at=created_at, updated_at=created_at)
        self._write(row)
        return row

    def update(self, project_id: str, **fields: Any) -> dict[str, Any]:
        """Полная перезапись строки; updated_at обновляется при каждой записи."""
        row = self.get(project_id)
        if row is None:
            raise KeyError(project_id)
        for k, v in fields.items():
            if k in _COLUMNS and k not in ("id", "created_at"):
                row[k] = v
        row["updated_at"] = now_iso()
        self._write(row)
        return row

    def delete(self, project_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def _write(self, row: dict[str, Any]) -> None:
        with self._conn:                 # транзакция + немедленный коммит
            self._conn.execute(_UPSERT, row)
