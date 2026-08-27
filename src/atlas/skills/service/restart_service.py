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
    SkillValidationError,
)


class RestartServiceSkill(Skill):

    name = "service.restart"

    description = (
        "Redémarre un service Windows en passant "
        "exclusivement par AtlasService. "
        "Utiliser le nom système du service, "
        "par exemple 'Spooler'."
    )

    risk_level = RiskLevel.ADMIN

    required_permission = None

    requires_service = True

    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Nom système exact du service "
                    "Windows à redémarrer. "
                    "Exemple : Spooler"
                ),
            },
        },
        "required": [
            "name",
        ],
        "additionalProperties": False,
    }

    def __init__(
        self,
        service_client: AtlasServiceClient,
    ) -> None:

        self.service_client = (
            service_client
        )

    def validate(
        self,
        **kwargs: Any,
    ) -> None:

        name = kwargs.get(
            "name"
        )

        if not isinstance(
            name,
            str,
        ):

            raise SkillValidationError(
                "Le nom du service doit "
                "être une chaîne."
            )

        if not name.strip():

            raise SkillValidationError(
                "Le nom du service ne peut "
                "pas être vide."
            )

        # Validation légère côté Atlas.exe.
        #
        # La validation de sécurité réelle
        # est répétée côté AtlasService.
        allowed_characters = (
            set(
                "abcdefghijklmnopqrstuvwxyz"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "0123456789"
                "_.-"
            )
        )

        if any(
            character
            not in allowed_characters
            for character in name.strip()
        ):

            raise SkillValidationError(
                "Le nom du service contient "
                "des caractères interdits."
            )

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        name = (
            kwargs["name"]
            .strip()
        )

        try:

            response = (
                self.service_client
                .restart_service(
                    name
                )
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