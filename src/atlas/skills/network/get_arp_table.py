from __future__ import annotations

import json
import subprocess
from typing import Any

from atlas.system.powershell import run_fixed_powershell

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


POWERSHELL_TIMEOUT_SECONDS = 12.0
MAX_ENTRIES = 500

POWERSHELL_SCRIPT = (
    "Get-NetNeighbor -AddressFamily IPv4,IPv6 | "
    "Select-Object "
    "IPAddress,"
    "LinkLayerAddress,"
    "State,"
    "InterfaceAlias,"
    "InterfaceIndex,"
    "AddressFamily | "
    "Sort-Object InterfaceAlias,IPAddress | "
    "ConvertTo-Json -Depth 3 -Compress"
)


class GetArpTableNetworkSkill(Skill):

    name = "network.get_arp_table"

    description = (
        "Récupère les voisins réseau connus par Windows, notamment "
        "les correspondances entre adresses IP et adresses MAC."
    )

    parameters = {
        "type": "object",
        "properties": {
            "interface": {
                "type": "string",
                "description": (
                    "Filtre optionnel sur le nom de l'interface réseau."
                ),
            },
            "state": {
                "type": "string",
                "description": (
                    "Filtre optionnel sur l'état du voisin réseau, "
                    "par exemple Reachable, Stale ou Permanent."
                ),
            },
        },
        "additionalProperties": False,
    }

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    def execute(
        self,
        interface: str = "",
        state: str = "",
        **kwargs: Any,
    ) -> SkillResult:

        if not isinstance(
            interface,
            str,
        ):

            return SkillResult(
                success=False,
                message=(
                    "Le filtre d'interface fourni est invalide."
                ),
            )

        if not isinstance(
            state,
            str,
        ):

            return SkillResult(
                success=False,
                message=(
                    "Le filtre d'état fourni est invalide."
                ),
            )

        interface_filter = (
            interface.strip().casefold()
        )

        state_filter = (
            state.strip().casefold()
        )

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
                    "La récupération de la table ARP/voisins "
                    "a dépassé le délai autorisé."
                ),
            )

        except OSError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible de récupérer la table ARP/voisins."
                ),
                data={
                    "error": str(exc),
                },
            )

        if completed.returncode != 0:

            return SkillResult(
                success=False,
                message=(
                    "Windows n'a pas pu retourner la table ARP/voisins."
                ),
                data={
                    "returncode": completed.returncode,
                    "stdout": completed.stdout.strip(),
                    "stderr": completed.stderr.strip(),
                },
            )

        raw_output = completed.stdout.strip()

        if not raw_output:

            entries: list[dict[str, Any]] = []

        else:

            try:

                parsed = json.loads(
                    raw_output
                )

            except json.JSONDecodeError as exc:

                return SkillResult(
                    success=False,
                    message=(
                        "La table ARP/voisins retournée par Windows "
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

                entries = [
                    parsed
                ]

            elif isinstance(
                parsed,
                list,
            ):

                entries = [
                    item
                    for item in parsed
                    if isinstance(
                        item,
                        dict,
                    )
                ]

            else:

                entries = []

        filtered_entries = []

        for entry in entries:

            if interface_filter:

                alias = str(
                    entry.get(
                        "InterfaceAlias",
                        "",
                    )
                ).casefold()

                if interface_filter not in alias:
                    continue

            if state_filter:

                entry_state = str(
                    entry.get(
                        "State",
                        "",
                    )
                ).casefold()

                if state_filter != entry_state:
                    continue

            filtered_entries.append(
                entry
            )

        truncated = (
            len(filtered_entries)
            > MAX_ENTRIES
        )

        if truncated:

            filtered_entries = (
                filtered_entries[
                    :MAX_ENTRIES
                ]
            )

        ipv4_count = 0
        ipv6_count = 0

        for entry in filtered_entries:

            address_family = str(
                entry.get(
                    "AddressFamily",
                    "",
                )
            )

            if address_family in {
                "2",
                "IPv4",
            }:
                ipv4_count += 1

            elif address_family in {
                "23",
                "IPv6",
            }:
                ipv6_count += 1

        return SkillResult(
            success=True,
            message=(
                f"{len(filtered_entries)} voisin(s) réseau récupéré(s)."
            ),
            data={
                "entries": filtered_entries,
                "count": len(
                    filtered_entries
                ),
                "ipv4_count": ipv4_count,
                "ipv6_count": ipv6_count,
                "interface_filter": (
                    interface.strip()
                ),
                "state_filter": (
                    state.strip()
                ),
                "truncated": truncated,
                "max_entries": MAX_ENTRIES,
            },
        )
