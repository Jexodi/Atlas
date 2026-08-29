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


class RenewDhcpSkill(Skill):

    name = "network.renew_dhcp"

    description = (
        "Renouvelle le bail DHCP d'une interface réseau Windows "
        "ou de toutes les interfaces DHCP si aucune interface "
        "n'est précisée."
    )

    risk_level = RiskLevel.ADMIN

    required_permission = None

    requires_service = True

    parameters = {
        "type": "object",
        "properties": {
            "adapter": {
                "type": "string",
                "description": (
                    "Nom exact de l'interface réseau à renouveler, "
                    "par exemple Ethernet ou Wi-Fi. Laisser vide pour "
                    "renouveler toutes les interfaces DHCP."
                ),
            },
        },
        "additionalProperties": False,
    }

    def __init__(
        self,
        service_client: SideronServiceClient,
    ) -> None:

        self.service_client = (
            service_client
        )

    def get_confirmation_message(
        self,
        **kwargs: Any,
    ) -> str:

        adapter = kwargs.get(
            "adapter"
        )

        if isinstance(adapter, str):
            adapter = adapter.strip()

        if adapter:

            return (
                "Voulez-vous renouveler le bail DHCP "
                f"de l'interface '{adapter}' ?"
            )

        return (
            "Voulez-vous renouveler les baux DHCP "
            "des interfaces réseau Windows ?"
        )

    def execute(
        self,
        adapter: str | None = None,
        **kwargs: Any,
    ) -> SkillResult:

        if adapter is not None:

            if not isinstance(
                adapter,
                str,
            ):

                return SkillResult(
                    success=False,
                    message=(
                        "Le nom de l'interface réseau "
                        "est invalide."
                    ),
                )

            adapter = adapter.strip()

            if not adapter:
                adapter = None

        try:

            response = (
                self.service_client
                .renew_dhcp(
                    adapter=adapter,
                )
            )

        except SideronServiceError as exc:

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
