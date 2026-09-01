from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import ScheduledTask


class AutomationRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    message TEXT NOT NULL,
                    run_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    completed_at TEXT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_scheduled_tasks_due
                ON scheduled_tasks(status, run_at)
                """
            )

    def create_reminder(self, *, message: str, run_at: datetime) -> ScheduledTask:
        now = datetime.now(timezone.utc)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO scheduled_tasks(kind, message, run_at, status, created_at)
                VALUES (?, ?, ?, 'pending', ?)
                """,
                ("reminder", message, self._serialize(run_at), self._serialize(now)),
            )
            task_id = int(cursor.lastrowid)
        return self.get(task_id)

    def get(self, task_id: int) -> ScheduledTask:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM scheduled_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            raise KeyError(task_id)
        return self._to_task(row)

    def list(self, *, status: str | None = None, limit: int = 100) -> list[ScheduledTask]:
        query = "SELECT * FROM scheduled_tasks"
        params: list[object] = []
        if status is not None:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY run_at ASC LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._to_task(row) for row in rows]

    def due(self, now: datetime, *, limit: int = 50) -> list[ScheduledTask]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM scheduled_tasks
                WHERE status = 'pending' AND run_at <= ?
                ORDER BY run_at ASC
                LIMIT ?
                """,
                (self._serialize(now), limit),
            ).fetchall()
        return [self._to_task(row) for row in rows]

    def complete(self, task_id: int, completed_at: datetime) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE scheduled_tasks
                SET status = 'completed', completed_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (self._serialize(completed_at), task_id),
            )
        return cursor.rowcount == 1

    def cancel(self, task_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE scheduled_tasks
                SET status = 'cancelled'
                WHERE id = ? AND status = 'pending'
                """,
                (task_id,),
            )
        return cursor.rowcount == 1

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _serialize(value: datetime) -> str:
        if value.tzinfo is None:
            raise ValueError("Une date avec fuseau horaire est requise.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _parse(value: str | None) -> datetime | None:
        if value is None:
            return None
        return datetime.fromisoformat(value)

    def _to_task(self, row: sqlite3.Row) -> ScheduledTask:
        return ScheduledTask(
            id=int(row["id"]),
            kind=str(row["kind"]),
            message=str(row["message"]),
            run_at=self._parse(str(row["run_at"])),
            status=str(row["status"]),
            created_at=self._parse(str(row["created_at"])),
            completed_at=self._parse(row["completed_at"]),
        )
