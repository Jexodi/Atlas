import subprocess

from atlas.security.risk import RiskLevel
from atlas.skills.base import (
    Skill,
    SkillResult,
    SkillValidationError,
)


class OpenAppSkill(Skill):

    name = "windows.open_app"

    description = "Ouvre une application Windows."

    parameters = {
        "type": "object",
        "properties": {
            "app": {
                "type": "string",
                "description": (
                    "Nom ou commande Windows de "
                    "l'application à lancer."
                ),
            },
        },
        "required": [
            "app",
        ],
        "additionalProperties": False,
    }

    risk_level = RiskLevel.SAFE

    required_permission = None

    requires_service = False

    def validate(
        self,
        **kwargs,
    ) -> None:

        app = kwargs.get("app")

        if app is None:
            raise SkillValidationError(
                "Le paramètre 'app' est obligatoire."
            )

        if not isinstance(app, str):
            raise SkillValidationError(
                "Le paramètre 'app' doit être une chaîne."
            )

        if not app.strip():
            raise SkillValidationError(
                "Le nom de l'application ne peut pas être vide."
            )

    def execute(
        self,
        **kwargs,
    ) -> SkillResult:

        app = kwargs["app"]

        subprocess.Popen(
            app,
            shell=True,
        )

        return SkillResult(
            success=True,
            message=f"Application lancée : {app}",
            data={
                "app": app,
            },
        )