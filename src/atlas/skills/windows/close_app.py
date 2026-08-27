import subprocess

from atlas.security.risk import RiskLevel
from atlas.skills.base import (
    Skill,
    SkillResult,
    SkillValidationError,
)


class CloseAppSkill(Skill):

    name = "windows.close_app"

    description = "Ferme une application Windows par son nom de processus."

    parameters = {
        "type": "object",
        "properties": {
            "process_name": {
                "type": "string",
                "description": (
                    "Nom du processus Windows à fermer, "
                    "par exemple notepad.exe."
                ),
            },
        },
        "required": [
            "process_name",
        ],
        "additionalProperties": False,
    }

    risk_level = RiskLevel.LOCAL_MODIFICATION

    required_permission = None

    requires_service = False

    def validate(
        self,
        **kwargs,
    ) -> None:

        process_name = kwargs.get("process_name")

        if process_name is None:
            raise SkillValidationError(
                "Le paramètre 'process_name' est obligatoire."
            )

        if not isinstance(process_name, str):
            raise SkillValidationError(
                "Le paramètre 'process_name' doit être une chaîne."
            )

        if not process_name.strip():
            raise SkillValidationError(
                "Le nom du processus ne peut pas être vide."
            )

    def execute(
        self,
        **kwargs,
    ) -> SkillResult:

        process_name = kwargs["process_name"]

        command = [
            "taskkill",
            "/IM",
            process_name,
            "/F",
        ]

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        if completed.returncode != 0:

            return SkillResult(
                success=False,
                message=(
                    completed.stderr.strip()
                    or completed.stdout.strip()
                    or "Impossible de fermer l'application."
                ),
            )

        return SkillResult(
            success=True,
            message=f"Application fermée : {process_name}",
            data={
                "process_name": process_name,
            },
        )