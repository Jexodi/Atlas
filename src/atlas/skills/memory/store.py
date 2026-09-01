from __future__ import annotations

from typing import Any

from atlas.memory import MemoryManager
from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class StoreMemorySkill(Skill):
    name = "memory.store"
    description = (
        "Enregistre ou met à jour une information durable utile dans la mémoire locale de SIDERON. "
        "À utiliser lorsque l'utilisateur demande explicitement de retenir une préférence, un alias "
        "ou un fait durable. Pour une information qui remplace une préférence existante, réutiliser "
        "une clé stable afin de mettre à jour le souvenir au lieu d'en créer un doublon. SIDERON normalise aussi les clés connues et peut réutiliser automatiquement une clé existante lorsque le concept correspond sans ambiguïté."
    )
    risk_level = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Information concise à mémoriser.",
            },
            "category": {
                "type": "string",
                "enum": sorted(MemoryManager.CATEGORIES),
                "description": "Catégorie logique du souvenir.",
            },
            "key": {
                "type": "string",
                "description": (
                    "Clé stable facultative décrivant le concept (ex. audio.volume.default). Les variantes de clés connues sont normalisées et une clé existante peut être réutilisée automatiquement pour éviter les contradictions."
                ),
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags facultatifs facilitant la recherche locale.",
            },
        },
        "required": ["content"],
        "additionalProperties": False,
    }

    def __init__(self, memory: MemoryManager) -> None:
        self.memory = memory

    def validate(self, **kwargs: Any) -> None:
        self.memory._clean_required_text(
            kwargs.get("content"),
            "Le contenu du souvenir",
            self.memory.MAX_CONTENT_LENGTH,
        )
        if "category" in kwargs:
            self.memory.validate_category(kwargs["category"])
        if "tags" in kwargs and not isinstance(kwargs["tags"], list):
            raise ValueError("Les tags mémoire doivent être une liste.")
        self.memory.normalize_tags(kwargs.get("tags") or ())

    def execute(self, **kwargs: Any) -> SkillResult:
        record = self.memory.store(
            content=kwargs["content"],
            category=kwargs.get("category", "fact"),
            key=kwargs.get("key"),
            source="user",
            tags=kwargs.get("tags") or (),
        )
        return SkillResult(
            success=True,
            message="L'information a été enregistrée dans la mémoire locale de SIDERON.",
            data=record.to_dict(),
        )
