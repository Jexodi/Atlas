from __future__ import annotations

import json
import sqlite3
import unicodedata

from pathlib import Path
from typing import Iterable

from atlas.memory.models import MemoryRecord


class MemoryRepositoryError(RuntimeError):
    pass


class MemoryRepository:
    """Stockage SQLite local de la mémoire persistante de SIDERON."""

    SCHEMA_VERSION = 1

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve(strict=False)

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        category TEXT NOT NULL,
                        memory_key TEXT NULL,
                        content TEXT NOT NULL,
                        source TEXT NOT NULL DEFAULT 'user',
                        tags_json TEXT NOT NULL DEFAULT '[]',
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE UNIQUE INDEX IF NOT EXISTS ux_memories_category_key
                        ON memories(category, memory_key)
                        WHERE memory_key IS NOT NULL;

                    CREATE INDEX IF NOT EXISTS ix_memories_category
                        ON memories(category);

                    CREATE INDEX IF NOT EXISTS ix_memories_updated_at
                        ON memories(updated_at DESC);
                    """
                )
                connection.execute(
                    """
                    INSERT INTO metadata(key, value)
                    VALUES('schema_version', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (str(self.SCHEMA_VERSION),),
                )
        except sqlite3.Error as exc:
            raise MemoryRepositoryError(
                f"Impossible d'initialiser la mémoire SIDERON : {exc}"
            ) from exc

    def store(
        self,
        *,
        category: str,
        content: str,
        key: str | None,
        source: str,
        tags: Iterable[str],
    ) -> MemoryRecord:
        tags_json = json.dumps(list(tags), ensure_ascii=False)

        try:
            with self._connect() as connection:
                if key is None:
                    cursor = connection.execute(
                        """
                        INSERT INTO memories(
                            category, content, memory_key, source, tags_json
                        )
                        VALUES(?, ?, NULL, ?, ?)
                        """,
                        (category, content, source, tags_json),
                    )
                    memory_id = int(cursor.lastrowid)
                else:
                    connection.execute(
                        """
                        INSERT INTO memories(
                            category, content, memory_key, source, tags_json
                        )
                        VALUES(?, ?, ?, ?, ?)
                        ON CONFLICT(category, memory_key)
                        WHERE memory_key IS NOT NULL
                        DO UPDATE SET
                            content = excluded.content,
                            source = excluded.source,
                            tags_json = excluded.tags_json,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (category, content, key, source, tags_json),
                    )
                    row = connection.execute(
                        """
                        SELECT id
                        FROM memories
                        WHERE category = ? AND memory_key = ?
                        """,
                        (category, key),
                    ).fetchone()
                    if row is None:
                        raise MemoryRepositoryError(
                            "Le souvenir enregistré n'a pas pu être relu."
                        )
                    memory_id = int(row["id"])

                record = self.get(memory_id, connection=connection)
                if record is None:
                    raise MemoryRepositoryError(
                        "Le souvenir enregistré n'a pas pu être relu."
                    )
                return record
        except sqlite3.Error as exc:
            raise MemoryRepositoryError(
                f"Impossible d'enregistrer le souvenir : {exc}"
            ) from exc

    def get(
        self,
        memory_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> MemoryRecord | None:
        owns_connection = connection is None
        current = connection or self._connect()

        try:
            row = current.execute(
                "SELECT * FROM memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
            return self._row_to_record(row) if row is not None else None
        finally:
            if owns_connection:
                current.close()

    def search(
        self,
        query: str,
        *,
        category: str | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """Recherche locale tolérante aux formulations naturelles.

        La première version utilisait un unique ``LIKE`` sur la phrase entière.
        Cela fonctionnait pour une recherche exacte comme ``volume`` mais pas
        pour une demande naturelle telle que ``mes préférences audio``.

        On charge ici un ensemble borné de souvenirs récents puis on les classe
        localement, sans appel réseau, avec une normalisation Unicode et un score
        donnant davantage de poids aux clés et aux tags.
        """

        sql = "SELECT * FROM memories"
        parameters: list[object] = []

        if category is not None:
            sql += " WHERE category = ?"
            parameters.append(category)

        # La mémoire personnelle reste volontairement compacte. Cette borne
        # empêche néanmoins une recherche de parcourir une base sans limite.
        sql += " ORDER BY updated_at DESC, id DESC LIMIT 1000"

        try:
            with self._connect() as connection:
                rows = connection.execute(sql, parameters).fetchall()
        except sqlite3.Error as exc:
            raise MemoryRepositoryError(
                f"Impossible de rechercher dans la mémoire : {exc}"
            ) from exc

        normalized_query = self._normalize_search_text(query)
        query_tokens = self._search_tokens(normalized_query)

        ranked: list[tuple[int, int, MemoryRecord]] = []

        for position, row in enumerate(rows):
            record = self._row_to_record(row)
            score = self._score_record(
                record,
                normalized_query=normalized_query,
                query_tokens=query_tokens,
            )

            if score > 0:
                # ``position`` conserve la récence comme critère secondaire.
                ranked.append((score, -position, record))

        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [record for _, _, record in ranked[:limit]]

    @classmethod
    def _score_record(
        cls,
        record: MemoryRecord,
        *,
        normalized_query: str,
        query_tokens: tuple[str, ...],
    ) -> int:
        content = cls._normalize_search_text(record.content)
        key = cls._normalize_search_text(record.key or "")
        tags = tuple(cls._normalize_search_text(tag) for tag in record.tags)
        tags_text = " ".join(tags)
        combined = " ".join(part for part in (key, tags_text, content) if part)

        score = 0

        if normalized_query and normalized_query in combined:
            score += 12

        for token in query_tokens:
            if token in key:
                score += 6
            if token in tags_text:
                score += 5
            if token in content:
                score += 3

        return score

    @staticmethod
    def _normalize_search_text(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value.casefold())
        without_accents = "".join(
            char for char in decomposed if not unicodedata.combining(char)
        )
        return " ".join(
            "".join(char if char.isalnum() else " " for char in without_accents).split()
        )

    @classmethod
    def _search_tokens(cls, normalized_query: str) -> tuple[str, ...]:
        stop_words = {
            "a", "au", "aux", "ce", "ces", "de", "des", "du", "en",
            "et", "est", "la", "le", "les", "ma", "mes", "mon", "que",
            "qui", "sur", "ta", "tes", "ton", "tu", "un", "une", "vous",
        }

        tokens: list[str] = []
        for token in normalized_query.split():
            if len(token) < 2 or token in stop_words:
                continue
            if token not in tokens:
                tokens.append(token)

        return tuple(tokens)

    def list(
        self,
        *,
        category: str | None = None,
        limit: int = 50,
    ) -> list[MemoryRecord]:
        sql = "SELECT * FROM memories"
        parameters: list[object] = []

        if category is not None:
            sql += " WHERE category = ?"
            parameters.append(category)

        sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
        parameters.append(limit)

        try:
            with self._connect() as connection:
                rows = connection.execute(sql, parameters).fetchall()
        except sqlite3.Error as exc:
            raise MemoryRepositoryError(
                f"Impossible de consulter la mémoire : {exc}"
            ) from exc

        return [self._row_to_record(row) for row in rows]

    def delete(self, memory_id: int) -> bool:
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM memories WHERE id = ?",
                    (memory_id,),
                )
                return cursor.rowcount > 0
        except sqlite3.Error as exc:
            raise MemoryRepositoryError(
                f"Impossible de supprimer le souvenir : {exc}"
            ) from exc

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        try:
            raw_tags = json.loads(row["tags_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            raw_tags = []

        tags = tuple(str(tag) for tag in raw_tags if isinstance(tag, str))

        return MemoryRecord(
            id=int(row["id"]),
            category=str(row["category"]),
            content=str(row["content"]),
            key=(str(row["memory_key"]) if row["memory_key"] is not None else None),
            source=str(row["source"]),
            tags=tags,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
