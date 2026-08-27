from __future__ import annotations

from typing import Any

from atlas.security.risk import (
    RiskLevel,
)

from atlas.service import (
    AtlasServiceClient,
    AtlasServiceError,
)

from atlas.skills.base import (
    Skill,
    SkillResult,
)


class FlushDnsSkill(Skill):

    name = "network.flush_dns"

    description = (
        "Vide le cache DNS local de Windows. "
        "À utiliser lorsqu'une résolution DNS "
        "semble obsolète ou incorrecte."
    )

    risk_level = RiskLevel.ADMIN

    required_permission = None

    requires_service = True

    parameters = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def __init__(
        self,
        service_client: AtlasServiceClient,
    ) -> None:

        self.service_client = (
            service_client
        )

    def get_confirmation_message(
        self,
        **kwargs: Any,
    ) -> str:

        return (
            "Voulez-vous vider le cache DNS "
            "de Windows ?"
        )

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        try:

            response = (
                self.service_client
                .flush_dns()
            )

        except AtlasServiceError as exc:

            return SkillResult(
                success=False,
                message=str(
                    exc
                ),
            )

        return SkillResult(
            success=(
                response.success
            ),
            message=(
                response.message
            ),
            data=(
                response.data
            ),
        )
