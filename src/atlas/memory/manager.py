from __future__ import annotations

from pathlib import Path
from typing import Iterable
import re
import unicodedata

from atlas.memory.models import MemoryRecord
from atlas.memory.repository import MemoryRepository


class MemoryValidationError(ValueError):
    pass


class MemoryManager:
    """API locale de haut niveau pour la mémoire persistante SIDERON."""

    CATEGORIES = frozenset(
        {
            "preference",
            "alias",
            "fact",
            "application",
            "project",
            "other",
        }
    )

    MAX_CONTENT_LENGTH = 8_000
    MAX_KEY_LENGTH = 200
    MAX_TAG_LENGTH = 80
    MAX_TAGS = 20

    def __init__(self, database_path: str | Path) -> None:
        self.repository = MemoryRepository(database_path)

    @property
    def database_path(self) -> Path:
        return self.repository.database_path

    def initialize(self) -> None:
        self.repository.initialize()

    def store(
        self,
        *,
        content: str,
        category: str = "fact",
        key: str | None = None,
        source: str = "user",
        tags: Iterable[str] | None = None,
    ) -> MemoryRecord:
        content = self._clean_required_text(
            content,
            "Le contenu du souvenir",
            self.MAX_CONTENT_LENGTH,
        )
        category = self.validate_category(category)
        key = self._clean_optional_text(key, self.MAX_KEY_LENGTH)
        source = self._clean_required_text(source, "La source", 80)
        normalized_tags = self.normalize_tags(tags or ())
        key = self.resolve_storage_key(
            category=category,
            key=key,
            content=content,
            tags=normalized_tags,
        )

        return self.repository.store(
            category=category,
            content=content,
            key=key,
            source=source,
            tags=normalized_tags,
        )


    def resolve_storage_key(
        self,
        *,
        category: str,
        key: str | None,
        content: str,
        tags: Iterable[str],
    ) -> str | None:
        """Retourne une clé stable et, si possible, réutilise celle d'un souvenir existant.

        Le LLM peut exprimer le même concept avec des clés légèrement différentes
        (``audio.volume``, ``preferred.volume``...). On normalise d'abord la syntaxe
        puis, pour les catégories où une valeur remplace naturellement l'ancienne,
        on réutilise une clé existante lorsqu'un concept unique correspond.
        """
        if key is None:
            return None

        normalized_key = self.normalize_key(key)
        if category not in {"preference", "alias"}:
            return normalized_key

        new_concepts = self._concept_tokens(normalized_key, content, tags)
        if not new_concepts:
            return normalized_key

        candidates: list[MemoryRecord] = []
        for record in self.repository.list(category=category, limit=200):
            if not record.key:
                continue
            existing_concepts = self._concept_tokens(
                self.normalize_key(record.key),
                record.content,
                record.tags,
            )
            if new_concepts & existing_concepts:
                candidates.append(record)

        # Un seul concept existant correspondant : on conserve sa clé originale
        # afin que l'UPSERT remplace le souvenir au lieu d'en créer un second.
        unique_keys = {record.key for record in candidates if record.key}
        if len(unique_keys) == 1:
            return next(iter(unique_keys))

        return normalized_key

    @classmethod
    def normalize_key(cls, value: str) -> str:
        cleaned = cls._clean_required_text(value, "La clé mémoire", cls.MAX_KEY_LENGTH)
        decomposed = unicodedata.normalize("NFKD", cleaned.casefold())
        ascii_like = "".join(
            char for char in decomposed if not unicodedata.combining(char)
        )
        tokens = [token for token in re.split(r"[^a-z0-9]+", ascii_like) if token]

        # Alias conservateurs pour les concepts déjà utilisés par SIDERON.
        aliases = {
            ("audio", "volume"): "audio.volume.default",
            ("default", "volume"): "audio.volume.default",
            ("preferred", "volume"): "audio.volume.default",
            ("preference", "volume"): "audio.volume.default",
            ("volume", "default"): "audio.volume.default",
            ("volume", "preferred"): "audio.volume.default",
            ("audio", "headset"): "audio.output.headset",
            ("audio", "headphones"): "audio.output.headset",
            ("preferred", "headset"): "audio.output.headset",
            ("preference", "headset"): "audio.output.headset",
        }
        token_tuple = tuple(tokens)
        if token_tuple in aliases:
            return aliases[token_tuple]

        return ".".join(tokens)

    @classmethod
    def _concept_tokens(
        cls,
        key: str,
        content: str,
        tags: Iterable[str],
    ) -> set[str]:
        raw = " ".join([key, content, *tags])
        decomposed = unicodedata.normalize("NFKD", raw.casefold())
        text = "".join(char for char in decomposed if not unicodedata.combining(char))
        tokens = {token for token in re.split(r"[^a-z0-9]+", text) if len(token) >= 3}

        synonyms = {
            "casque": "headset",
            "headphones": "headset",
            "micro": "microphone",
            "mic": "microphone",
            "son": "audio",
            "volume": "volume",
        }
        tokens = {synonyms.get(token, token) for token in tokens}

        generic = {
            "audio", "default", "preferred", "preference", "prefere", "preferer",
            "utilise", "utiliser", "mon", "ma", "mes", "est", "les", "des",
            "pour", "avec", "dans", "sideron",
        }
        return tokens - generic

    def search(
        self,
        query: str,
        *,
        category: str | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        query = self._clean_required_text(query, "La recherche", 500)
        category = self.validate_category(category) if category is not None else None
        limit = self.validate_limit(limit, maximum=50)
        return self.repository.search(query, category=category, limit=limit)

    def list(
        self,
        *,
        category: str | None = None,
        limit: int = 50,
    ) -> list[MemoryRecord]:
        category = self.validate_category(category) if category is not None else None
        limit = self.validate_limit(limit, maximum=200)
        return self.repository.list(category=category, limit=limit)

    def get(self, memory_id: int) -> MemoryRecord | None:
        return self.repository.get(self.validate_memory_id(memory_id))

    def delete(self, memory_id: int) -> bool:
        return self.repository.delete(self.validate_memory_id(memory_id))

    @classmethod
    def validate_category(cls, category: str) -> str:
        if not isinstance(category, str):
            raise MemoryValidationError("La catégorie mémoire doit être une chaîne.")

        normalized = category.strip().lower()
        if normalized not in cls.CATEGORIES:
            allowed = ", ".join(sorted(cls.CATEGORIES))
            raise MemoryValidationError(
                f"Catégorie mémoire inconnue '{category}'. Valeurs autorisées : {allowed}."
            )
        return normalized

    @staticmethod
    def validate_memory_id(memory_id: int) -> int:
        if isinstance(memory_id, bool) or not isinstance(memory_id, int) or memory_id <= 0:
            raise MemoryValidationError("L'identifiant mémoire doit être un entier positif.")
        return memory_id

    @staticmethod
    def validate_limit(limit: int, *, maximum: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise MemoryValidationError("La limite doit être un entier.")
        if limit < 1 or limit > maximum:
            raise MemoryValidationError(f"La limite doit être comprise entre 1 et {maximum}.")
        return limit

    @classmethod
    def normalize_tags(cls, tags: Iterable[str]) -> tuple[str, ...]:
        normalized: list[str] = []
        for tag in tags:
            if not isinstance(tag, str):
                raise MemoryValidationError("Chaque tag mémoire doit être une chaîne.")
            cleaned = tag.strip().lower()
            if not cleaned:
                continue
            if len(cleaned) > cls.MAX_TAG_LENGTH:
                raise MemoryValidationError(
                    f"Un tag mémoire ne peut pas dépasser {cls.MAX_TAG_LENGTH} caractères."
                )
            if cleaned not in normalized:
                normalized.append(cleaned)
            if len(normalized) > cls.MAX_TAGS:
                raise MemoryValidationError(
                    f"Un souvenir ne peut pas contenir plus de {cls.MAX_TAGS} tags."
                )
        return tuple(normalized)

    @staticmethod
    def _clean_required_text(value: str, label: str, maximum: int) -> str:
        if not isinstance(value, str):
            raise MemoryValidationError(f"{label} doit être une chaîne.")
        cleaned = value.strip()
        if not cleaned:
            raise MemoryValidationError(f"{label} ne peut pas être vide.")
        if len(cleaned) > maximum:
            raise MemoryValidationError(f"{label} ne peut pas dépasser {maximum} caractères.")
        return cleaned

    @staticmethod
    def _clean_optional_text(value: str | None, maximum: int) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise MemoryValidationError("La clé mémoire doit être une chaîne.")
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) > maximum:
            raise MemoryValidationError(
                f"La clé mémoire ne peut pas dépasser {maximum} caractères."
            )
        return cleaned
