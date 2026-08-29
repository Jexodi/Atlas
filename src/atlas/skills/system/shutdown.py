from __future__ import annotations

from typing import Any

from atlas.security.risk import (
    RiskLevel,
)

from atlas.service import (
    SideronServiceClient,
    SideronServiceError,
)

from atlas.skills.base import (
    Skill,
    SkillResult,
)


class ShutdownComputerSkill(Skill):

    name = "system.shutdown"

    description = (
        "Arrête complètement Windows. "
        "Cette action éteint l'ordinateur "
        "et nécessite toujours une confirmation "
        "explicite de l'utilisateur."
    )

    risk_level = RiskLevel.ADMIN

    required_permission = None

    requires_service = True

    always_requires_confirmation = True

    parameters = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def __init__(
        self,
        service_client: SideronServiceClient,
    ) -> None:

        self.service_client = (
            service_client
        )

    def validate(
        self,
        **kwargs: Any,
    ) -> None:

        pass

    def get_confirmation_message(
        self,
        **kwargs: Any,
    ) -> str:

        return (
            "Confirmez-vous l'arrêt complet "
            "de l'ordinateur ?"
        )

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        try:

            response = (
                self.service_client
                .shutdown_computer()
            )

        except SideronServiceError as exc:

            return SkillResult(
                success=False,
                message=str(
                    exc
                ),
            )

        return SkillResult(
            success=response.success,
            message=response.message,
            data=response.data,
        )