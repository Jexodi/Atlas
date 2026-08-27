from __future__ import annotations

import json
import subprocess
from typing import Any

from atlas.system.powershell import run_fixed_powershell

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


POWERSHELL_TIMEOUT_SECONDS = 12.0

POWERSHELL_SCRIPT = (
    "Get-NetRoute | "
    "Select-Object "
    "AddressFamily,"
    "DestinationPrefix,"
    "NextHop,"
    "InterfaceAlias,"
    "InterfaceIndex,"
    "RouteMetric,"
    "Protocol,"
    "State,"
    "Store | "
    "Sort-Object AddressFamily,RouteMetric,DestinationPrefix | "
    "ConvertTo-Json -Depth 3 -Compress"
)


class GetRoutesNetworkSkill(Skill):

    name = "network.get_routes"

    description = (
        "Récupère la table de routage Windows, notamment les routes, "
        "passerelles, interfaces et métriques."
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

            completed = run_fixed_powershell(
                POWERSHELL_SCRIPT,
                timeout=POWERSHELL_TIMEOUT_SECONDS,
            )

        except FileNotFoundError:

            return SkillResult(
                success=False,
                message=(
                    "PowerShell est introuvable sur ce système."
                ),
            )

        except subprocess.TimeoutExpired:

            return SkillResult(
                success=False,
                message=(
                    "La récupération de la table de routage "
                    "a dépassé le délai autorisé."
                ),
            )

        except OSError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible de récupérer la table de routage."
                ),
                data={
                    "error": str(exc),
                },
            )

        if completed.returncode != 0:

            return SkillResult(
                success=False,
                message=(
                    "Windows n'a pas pu retourner la table de routage."
                ),
                data={
                    "returncode": completed.returncode,
                    "stdout": completed.stdout.strip(),
                    "stderr": completed.stderr.strip(),
                },
            )

        raw_output = completed.stdout.strip()

        if not raw_output:

            routes: list[dict[str, Any]] = []

        else:

            try:

                parsed = json.loads(
                    raw_output
                )

            except json.JSONDecodeError as exc:

                return SkillResult(
                    success=False,
                    message=(
                        "La table de routage retournée par Windows "
                        "n'a pas pu être interprétée."
                    ),
                    data={
                        "error": str(exc),
                        "raw": raw_output,
                    },
                )

            if isinstance(
                parsed,
                dict,
            ):

                routes = [
                    parsed
                ]

            elif isinstance(
                parsed,
                list,
            ):

                routes = [
                    route
                    for route in parsed
                    if isinstance(
                        route,
                        dict,
                    )
                ]

            else:

                routes = []

        default_routes = []

        for route in routes:

            destination = route.get(
                "DestinationPrefix"
            )

            if destination in {
                "0.0.0.0/0",
                "::/0",
            }:

                default_routes.append(
                    route
                )

        return SkillResult(
            success=True,
            message=(
                f"{len(routes)} route(s) réseau récupérée(s), "
                f"dont {len(default_routes)} route(s) par défaut."
            ),
            data={
                "routes": routes,
                "default_routes": default_routes,
                "count": len(routes),
                "default_count": len(
                    default_routes
                ),
            },
        )
