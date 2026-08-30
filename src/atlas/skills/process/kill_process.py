from __future__ import annotations

from typing import Any

import psutil

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
    SkillValidationError,
)


class KillProcessSkill(Skill):

    name = "process.kill"

    description = (
        "Arrête un processus Windows précis à partir "
        "de son PID. Utiliser process.list pour "
        "identifier le bon PID avant l'arrêt."
    )

    risk_level = RiskLevel.ADMIN

    required_permission = None

    requires_service = True

    parameters = {
        "type": "object",
        "properties": {
            "pid": {
                "type": "integer",
                "minimum": 1,
                "description": (
                    "PID exact du processus Windows "
                    "à arrêter."
                ),
            },
        },
        "required": [
            "pid",
        ],
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

        pid = kwargs.get(
            "pid"
        )

        if isinstance(
            pid,
            bool,
        ):

            raise SkillValidationError(
                "Le PID doit être un entier positif."
            )

        if not isinstance(
            pid,
            int,
        ):

            raise SkillValidationError(
                "Le PID doit être un entier."
            )

        if pid <= 0:

            raise SkillValidationError(
                "Le PID doit être supérieur à zéro."
            )

    def get_confirmation_message(
        self,
        **kwargs: Any,
    ) -> str:

        pid = kwargs.get(
            "pid"
        )

        try:

            process_name = (
                psutil.Process(
                    pid
                ).name()
            )

        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
            OSError,
        ):

            process_name = (
                "processus inconnu"
            )

        return (
            f"Voulez-vous arrêter le processus "
            f"'{process_name}' (PID {pid}) ?"
        )

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        pid = kwargs[
            "pid"
        ]

        try:

            process = psutil.Process(
                pid
            )

            process_name = (
                process.name()
                or ""
            )

        except psutil.NoSuchProcess:

            return SkillResult(
                success=False,
                message=(
                    f"Le processus PID {pid} "
                    "est introuvable."
                ),
                data={
                    "pid": pid,
                },
            )

        except psutil.AccessDenied:

            return SkillResult(
                success=False,
                message=(
                    f"Impossible de lire les informations "
                    f"du processus PID {pid}."
                ),
                data={
                    "pid": pid,
                },
            )

        except OSError as exc:

            return SkillResult(
                success=False,
                message=(
                    f"Impossible d'identifier le processus "
                    f"PID {pid} : {exc}"
                ),
                data={
                    "pid": pid,
                },
            )

        try:

            response = (
                self.service_client
                .kill_process(
                    pid=pid,
                    expected_name=(
                        process_name
                    ),
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
