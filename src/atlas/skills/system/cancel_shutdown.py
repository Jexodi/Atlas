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


class CancelShutdownSkill(Skill):

    name = "system.cancel_shutdown"

    description = (
        "Annule un arrêt ou un redémarrage "
        "de Windows déjà programmé. "
        "Utiliser cette action lorsqu'un "
        "arrêt ou un redémarrage doit être annulé."
    )

    risk_level = RiskLevel.SAFE

    required_permission = None

    requires_service = True

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

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        try:

            response = (
                self.service_client
                .cancel_shutdown()
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