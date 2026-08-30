from __future__ import annotations

import ctypes

from atlas.security.risk import (
    RiskLevel,
)

from atlas.skills.base import (
    Skill,
    SkillResult,
)


class LockComputerSkill(Skill):

    name = "system.lock"

    description = (
        "Verrouille immédiatement la session "
        "Windows actuellement ouverte."
    )

    risk_level = RiskLevel.SAFE

    required_permission = None

    parameters = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def validate(
        self,
        **kwargs,
    ) -> None:

        pass

    def execute(
        self,
        **kwargs,
    ) -> SkillResult:

        try:

            success = (
                ctypes.windll.user32
                .LockWorkStation()
            )

        except Exception as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible de verrouiller "
                    "la session Windows."
                ),
                data={
                    "error": str(
                        exc
                    ),
                },
            )

        if not success:

            return SkillResult(
                success=False,
                message=(
                    "Windows a refusé le "
                    "verrouillage de la session."
                ),
            )

        return SkillResult(
            success=True,
            message=(
                "La session Windows a été "
                "verrouillée."
            ),
        )