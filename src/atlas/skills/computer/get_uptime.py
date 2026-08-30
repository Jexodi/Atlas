from __future__ import annotations

from datetime import datetime
from typing import Any

import psutil

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class GetComputerUptimeSkill(Skill):

    name = "computer.get_uptime"

    description = (
        "Récupère depuis combien de temps Windows est démarré "
        "ainsi que la date et l'heure du dernier démarrage."
    )

    parameters = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        try:

            boot_timestamp = (
                psutil.boot_time()
            )

        except (
            OSError,
            RuntimeError,
        ) as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible de récupérer le temps "
                    "de fonctionnement de Windows."
                ),
                data={
                    "error": str(exc),
                },
            )

        now = datetime.now()

        boot_time = datetime.fromtimestamp(
            boot_timestamp
        )

        uptime_seconds = max(
            0,
            int(
                (
                    now
                    - boot_time
                ).total_seconds()
            ),
        )

        days, remainder = divmod(
            uptime_seconds,
            86400,
        )

        hours, remainder = divmod(
            remainder,
            3600,
        )

        minutes, seconds = divmod(
            remainder,
            60,
        )

        parts = []

        if days:

            parts.append(
                f"{days} jour"
                + (
                    "s"
                    if days != 1
                    else ""
                )
            )

        if hours or days:

            parts.append(
                f"{hours} heure"
                + (
                    "s"
                    if hours != 1
                    else ""
                )
            )

        if minutes or hours or days:

            parts.append(
                f"{minutes} minute"
                + (
                    "s"
                    if minutes != 1
                    else ""
                )
            )

        if not parts:

            parts.append(
                f"{seconds} seconde"
                + (
                    "s"
                    if seconds != 1
                    else ""
                )
            )

        human_uptime = ", ".join(
            parts
        )

        return SkillResult(
            success=True,
            message=(
                "Windows fonctionne depuis "
                f"{human_uptime}."
            ),
            data={
                "uptime_seconds": (
                    uptime_seconds
                ),
                "days": days,
                "hours": hours,
                "minutes": minutes,
                "seconds": seconds,
                "boot_time": (
                    boot_time.isoformat(
                        timespec="seconds"
                    )
                ),
                "current_time": (
                    now.isoformat(
                        timespec="seconds"
                    )
                ),
            },
        )
