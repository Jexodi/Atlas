from __future__ import annotations

import os
from typing import Any

import psutil

from atlas.security.risk import RiskLevel

from atlas.skills.base import (
    Skill,
    SkillResult,
)


class ListServicesSkill(Skill):

    name = "service.list"

    description = (
        "Liste les services Windows installés sur le PC "
        "avec leur nom, nom d'affichage, état et type "
        "de démarrage. Cette opération est strictement "
        "en lecture seule."
    )

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    parameters = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": [
                    "all",
                    "running",
                    "stopped",
                    "paused",
                ],
                "description": (
                    "Filtre optionnel sur l'état du service. "
                    "Utiliser 'all' pour tous les services."
                ),
                "default": "all",
            },
        },
        "required": [],
        "additionalProperties": False,
    }

    def validate(
        self,
        **kwargs: Any,
    ) -> None:

        status = kwargs.get(
            "status",
            "all",
        )

        if status not in {
            "all",
            "running",
            "stopped",
            "paused",
        }:

            raise ValueError(
                "Le filtre status doit être "
                "'all', 'running', 'stopped' ou 'paused'."
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

        status_filter = kwargs.get(
            "status",
            "all",
        )

        services: list[
            dict[str, Any]
        ] = []

        try:

            iterator = (
                psutil.win_service_iter()
            )

        except Exception as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible d'obtenir la liste "
                    f"des services Windows : {exc}"
                ),
            )

        for service in iterator:

            try:

                service_status = (
                    service.status()
                )

                if (
                    status_filter != "all"
                    and service_status
                    != status_filter
                ):

                    continue

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

                    pid = service.pid()

                except (
                    psutil.AccessDenied,
                    OSError,
                ):

                    pid = None

                services.append(
                    {
                        "name": (
                            service.name()
                        ),
                        "display_name": (
                            service.display_name()
                        ),
                        "status": (
                            service_status
                        ),
                        "start_type": (
                            start_type
                        ),
                        "pid": pid,
                    }
                )

            except (
                psutil.AccessDenied,
                psutil.NoSuchProcess,
                OSError,
            ):

                # Un service inaccessible ou disparu
                # pendant l'énumération ne doit pas
                # faire échouer toute la commande.
                continue

        services.sort(
            key=lambda item: (
                (
                    item.get(
                        "display_name"
                    )
                    or item["name"]
                ).casefold()
            )
        )

        if status_filter == "all":

            message = (
                f"{len(services)} service(s) "
                "Windows trouvé(s)."
            )

        else:

            message = (
                f"{len(services)} service(s) "
                f"avec l'état '{status_filter}'."
            )

        return SkillResult(
            success=True,
            message=message,
            data={
                "count": len(
                    services
                ),
                "filter": (
                    status_filter
                ),
                "services": services,
            },
        )