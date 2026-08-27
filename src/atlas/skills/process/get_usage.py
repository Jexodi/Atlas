import psutil

from atlas.security.risk import RiskLevel
from atlas.skills.base import (
    Skill,
    SkillResult,
    SkillValidationError,
)


class GetProcessUsageSkill(Skill):

    name = "process.get_usage"

    description = "Retourne l'utilisation CPU et mémoire d'un processus."

    parameters = {
        "type": "object",
        "properties": {
            "process_name": {
                "type": "string",
                "description": (
                    "Nom exact du processus Windows, "
                    "par exemple chrome.exe."
                ),
            },
        },
        "required": [
            "process_name",
        ],
        "additionalProperties": False,
    }

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    def validate(
        self,
        **kwargs,
    ) -> None:

        process_name = kwargs.get(
            "process_name"
        )

        if process_name is None:
            raise SkillValidationError(
                "Le paramètre 'process_name' est obligatoire."
            )

        if not isinstance(
            process_name,
            str,
        ):
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

        process_name = kwargs[
            "process_name"
        ].lower()

        matches = []

        for process in psutil.process_iter(
            [
                "pid",
                "name",
                "memory_percent",
            ]
        ):

            try:

                name = (
                    process.info["name"]
                    or ""
                )

                if name.lower() != process_name:
                    continue

                matches.append(
                    {
                        "pid": process.info["pid"],
                        "name": name,
                        "memory_percent": round(
                            process.info["memory_percent"],
                            2,
                        ),
                    }
                )

            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied,
            ):
                continue

        if not matches:

            return SkillResult(
                success=False,
                message=(
                    f"Aucun processus trouvé : {process_name}"
                ),
            )

        return SkillResult(
            success=True,
            message=(
                f"{len(matches)} processus trouvé(s)."
            ),
            data={
                "processes": matches,
            },
        )