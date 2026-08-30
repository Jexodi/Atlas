from __future__ import annotations

from typing import Any

import psutil

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class GetComputerBatterySkill(Skill):

    name = "computer.get_battery"

    description = (
        "Récupère l'état de la batterie de l'ordinateur, notamment "
        "le niveau de charge, l'alimentation secteur et le temps restant."
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

            battery = (
                psutil.sensors_battery()
            )

        except (
            OSError,
            RuntimeError,
        ) as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible de récupérer l'état de la batterie."
                ),
                data={
                    "error": str(exc),
                },
            )

        if battery is None:

            return SkillResult(
                success=True,
                message=(
                    "Aucune batterie n'a été détectée sur cet ordinateur."
                ),
                data={
                    "battery_present": False,
                },
            )

        percent = round(
            float(
                battery.percent
            ),
            1,
        )

        plugged = bool(
            battery.power_plugged
        )

        seconds_left = battery.secsleft

        unlimited_value = getattr(
            psutil,
            "POWER_TIME_UNLIMITED",
            -2,
        )

        unknown_value = getattr(
            psutil,
            "POWER_TIME_UNKNOWN",
            -1,
        )

        time_remaining_seconds = None
        time_remaining_text = None

        if (
            isinstance(
                seconds_left,
                (int, float),
            )
            and seconds_left >= 0
            and seconds_left
            not in {
                unlimited_value,
                unknown_value,
            }
        ):

            time_remaining_seconds = int(
                seconds_left
            )

            hours, remainder = divmod(
                time_remaining_seconds,
                3600,
            )

            minutes, _ = divmod(
                remainder,
                60,
            )

            if hours > 0:

                time_remaining_text = (
                    f"{hours} h {minutes} min"
                )

            else:

                time_remaining_text = (
                    f"{minutes} min"
                )

        if plugged:

            message = (
                f"La batterie est à {percent} % "
                "et l'ordinateur est branché sur secteur."
            )

        elif time_remaining_text:

            message = (
                f"La batterie est à {percent} %, "
                f"avec environ {time_remaining_text} restante(s)."
            )

        else:

            message = (
                f"La batterie est à {percent} % "
                "et l'ordinateur fonctionne sur batterie."
            )

        return SkillResult(
            success=True,
            message=message,
            data={
                "battery_present": True,
                "percent": percent,
                "power_plugged": plugged,
                "time_remaining_seconds": (
                    time_remaining_seconds
                ),
                "time_remaining_text": (
                    time_remaining_text
                ),
            },
        )
