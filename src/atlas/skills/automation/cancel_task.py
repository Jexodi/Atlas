from __future__ import annotations

from typing import Any

from atlas.automation import AutomationManager
from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class CancelAutomationTaskSkill(Skill):
    name = "automation.cancel"
    description = "Annule une automatisation SIDERON encore en attente."
    risk_level = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "minimum": 1, "description": "Identifiant de l'automatisation."}
        },
        "required": ["id"],
        "additionalProperties": False,
    }

    def __init__(self, automation: AutomationManager) -> None:
        self.automation = automation

    def validate(self, **kwargs: Any) -> None:
        self.automation.validate_task_id(kwargs.get("id"))

    def execute(self, **kwargs: Any) -> SkillResult:
        task_id = kwargs["id"]
        if not self.automation.cancel(task_id):
            return SkillResult(
                success=False,
                message="Cette automatisation est introuvable ou n'est plus en attente.",
            )
        return SkillResult(
            success=True,
            message=f"Automatisation #{task_id} annulée.",
            data={"id": task_id},
        )
