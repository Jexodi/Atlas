from __future__ import annotations

from typing import Any

from atlas.memory import MemoryManager
from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class ListMemoriesSkill(Skill):
    name = "memory.list"
    description = (
        "Liste les souvenirs persistants enregistrés localement par SIDERON, éventuellement filtrés par catégorie."
    )
    risk_level = RiskLevel.READ_ONLY
    parameters = {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": sorted(MemoryManager.CATEGORIES),
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
            },
        },
        "required": [],
        "additionalProperties": False,
    }

    def __init__(self, memory: MemoryManager) -> None:
        self.memory = memory

    def validate(self, **kwargs: Any) -> None:
        if kwargs.get("category") is not None:
            self.memory.validate_category(kwargs["category"])
        self.memory.validate_limit(kwargs.get("limit", 50), maximum=200)

    def execute(self, **kwargs: Any) -> SkillResult:
        records = self.memory.list(
            category=kwargs.get("category"),
            limit=kwargs.get("limit", 50),
        )
        return SkillResult(
            success=True,
            message=f"{len(records)} souvenir(s) présent(s) dans la mémoire locale.",
            data={"memories": [record.to_dict() for record in records]},
        )
