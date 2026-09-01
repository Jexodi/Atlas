from __future__ import annotations

from typing import Any

from atlas.automation import AutomationManager
from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class CreateReminderSkill(Skill):
    name = "automation.reminder.create"
    description = (
        "Crée un rappel local persistant. Pour une durée relative comme 'dans 30 minutes', "
        "utiliser delay_seconds. Pour une date absolue, utiliser run_at au format ISO 8601 avec fuseau horaire."
    )
    risk_level = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Texte à rappeler à l'utilisateur."},
            "delay_seconds": {
                "type": "integer",
                "minimum": 1,
                "maximum": AutomationManager.MAX_DELAY_SECONDS,
                "description": "Délai relatif en secondes avant le rappel.",
            },
            "run_at": {
                "type": "string",
                "description": "Date/heure ISO 8601 absolue avec fuseau horaire.",
            },
        },
        "required": ["message"],
        "additionalProperties": False,
    }

    def __init__(self, automation: AutomationManager) -> None:
        self.automation = automation

    def validate(self, **kwargs: Any) -> None:
        self.automation.validate_message(kwargs.get("message"))
        delay = kwargs.get("delay_seconds")
        run_at = kwargs.get("run_at")
        if (delay is None) == (run_at is None):
            raise ValueError("Indiquez soit delay_seconds, soit run_at.")
        if delay is not None:
            self.automation.validate_delay(delay)
        if run_at is not None:
            self.automation.parse_run_at(run_at)

    def execute(self, **kwargs: Any) -> SkillResult:
        task = self.automation.create_reminder(
            message=kwargs["message"],
            delay_seconds=kwargs.get("delay_seconds"),
            run_at=kwargs.get("run_at"),
        )
        return SkillResult(
            success=True,
            message=f"Rappel planifié (#{task.id}) pour {task.run_at.isoformat()}.",
            data=task.to_dict(),
        )
