from __future__ import annotations

import os
from typing import Any

import psutil

from atlas.security.risk import RiskLevel

from atlas.skills.base import (
    Skill,
    SkillResult,
    SkillValidationError,
)


class GetServiceStatusSkill(Skill):

    name = "service.get_status"

    description = (
        "Retourne les informations détaillées d'un "
        "service Windows : état, type de démarrage, "
        "PID, compte de service, chemin binaire et "
        "description. Cette opération est en lecture seule. "
        "Le paramètre name doit correspondre au nom système "
        "du service Windows, par exemple 'Spooler'."
    )

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Nom système du service Windows. "
                    "Exemple : Spooler"
                ),
            },
        },
        "required": [
            "name",
        ],
        "additionalProperties": False,
    }

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
                "Le nom du service doit être une chaîne."
            )

        if not name.strip():

            raise SkillValidationError(
                "Le nom du service ne peut pas être vide."
            )

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        if os.name != "nt":

            return SkillResult(
                success=False,
                message=(
                    "La gestion des services Sideron "
                    "est disponible uniquement sous Windows."
                ),
            )

        name = (
            kwargs["name"]
            .strip()
        )

        try:

            service = (
                psutil.win_service_get(
                    name
                )
            )

        except psutil.NoSuchProcess:

            return SkillResult(
                success=False,
                message=(
                    f"Le service Windows '{name}' "
                    "est introuvable."
                ),
            )

        except Exception as exc:

            return SkillResult(
                success=False,
                message=(
                    f"Impossible d'accéder au service "
                    f"'{name}' : {exc}"
                ),
            )

        try:

            service_name = (
                service.name()
            )

            display_name = (
                service.display_name()
            )

            status = (
                service.status()
            )

        except (
            psutil.AccessDenied,
            psutil.NoSuchProcess,
            OSError,
        ) as exc:

            return SkillResult(
                success=False,
                message=(
                    f"Impossible de lire l'état du "
                    f"service '{name}' : {exc}"
                ),
            )

        try:

            start_type = (
                service.start_type()
            )

        except (
            psutil.AccessDenied,
            OSError,
        ):

            start_type = None

        try:

            pid = (
                service.pid()
            )

        except (
            psutil.AccessDenied,
            OSError,
        ):

            pid = None

        try:

            username = (
                service.username()
            )

        except (
            psutil.AccessDenied,
            OSError,
        ):

            username = None

        try:

            binpath = (
                service.binpath()
            )

        except (
            psutil.AccessDenied,
            OSError,
        ):

            binpath = None

        try:

            description = (
                service.description()
            )

        except (
            psutil.AccessDenied,
            OSError,
        ):

            description = None

        return SkillResult(
            success=True,
            message=(
                f"Le service '{display_name}' "
                f"est actuellement '{status}'."
            ),
            data={
                "name": (
                    service_name
                ),
                "display_name": (
                    display_name
                ),
                "status": (
                    status
                ),
                "start_type": (
                    start_type
                ),
                "pid": pid,
                "username": (
                    username
                ),
                "binpath": (
                    binpath
                ),
                "description": (
                    description
                ),
            },
        )