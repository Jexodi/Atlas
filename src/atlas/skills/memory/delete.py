from __future__ import annotations

from typing import Any

from atlas.memory import MemoryManager
from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class DeleteMemorySkill(Skill):
    name = "memory.delete"
    description = (
        "Supprime un souvenir précis de la mémoire persistante locale de SIDERON. "
        "La suppression exige une confirmation explicite."
    )
    risk_level = RiskLevel.SAFE
    always_requires_confirmation = True
    parameters = {
        "type": "object",
        "properties": {
            "memory_id": {
                "type": "integer",
                "minimum": 1,
                "description": "Identifiant exact du souvenir à oublier.",
            },
        },
        "required": ["memory_id"],
        "additionalProperties": False,
    }

    def __init__(self, memory: MemoryManager) -> None:
        self.memory = memory

    def validate(self, **kwargs: Any) -> None:
        self.memory.validate_memory_id(kwargs.get("memory_id"))

    def get_confirmation_message(self, **kwargs: Any) -> str:
        memory_id = self.memory.validate_memory_id(kwargs["memory_id"])
        record = self.memory.get(memory_id)
        if record is None:
            return f"Le souvenir n°{memory_id} n'existe plus dans la mémoire SIDERON."
        preview = record.content
        if len(preview) > 100:
            preview = preview[:97].rstrip() + "..."
        return f"Confirmez-vous que SIDERON doit oublier le souvenir n°{memory_id} : « {preview} » ?"

    def execute(self, **kwargs: Any) -> SkillResult:
        memory_id = self.memory.validate_memory_id(kwargs["memory_id"])
        deleted = self.memory.delete(memory_id)
        if not deleted:
            return SkillResult(
                success=False,
                message=f"Le souvenir n°{memory_id} est introuvable.",
                data={"memory_id": memory_id, "deleted": False},
            )
        return SkillResult(
            success=True,
            message=f"Le souvenir n°{memory_id} a été supprimé de la mémoire locale de SIDERON.",
            data={"memory_id": memory_id, "deleted": True},
        )
