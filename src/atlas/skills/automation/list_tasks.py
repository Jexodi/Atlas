from __future__ import annotations

from typing import Any

from atlas.automation import AutomationManager
from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class ListAutomationTasksSkill(Skill):
    name = "automation.list"
    description = "Liste les automatisations locales persistantes de SIDERON."
    risk_level = RiskLevel.READ_ONLY
    parameters = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": sorted(AutomationManager.STATUSES),
                "description": "Statut à afficher. Par défaut : pending.",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
        },
        "required": [],
        "additionalProperties": False,
    }

    def __init__(self, automation: AutomationManager) -> None:
        self.automation = automation

    def validate(self, **kwargs: Any) -> None:
        status = kwargs.get("status", "pending")
        if status not in self.automation.STATUSES:
            raise ValueError("Statut invalide.")
        limit = kwargs.get("limit", 100)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("La limite doit être comprise entre 1 et 200.")

    def execute(self, **kwargs: Any) -> SkillResult:
        tasks = self.automation.list(
            status=kwargs.get("status", "pending"),
            limit=kwargs.get("limit", 100),
        )
        return SkillResult(
            success=True,
            message=f"{len(tasks)} automatisation(s) trouvée(s).",
            data={"tasks": [task.to_dict() for task in tasks]},
        )
