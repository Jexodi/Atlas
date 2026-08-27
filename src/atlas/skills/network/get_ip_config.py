from __future__ import annotations

import json
import subprocess
from typing import Any

from atlas.system.powershell import run_fixed_powershell

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


POWERSHELL_TIMEOUT_SECONDS = 15.0

POWERSHELL_COMMAND = (
    "Get-CimInstance Win32_NetworkAdapterConfiguration | "
    "Where-Object { $_.IPEnabled -eq $true } | "
    "Select-Object Description,InterfaceIndex,MACAddress,DHCPEnabled,"
    "DHCPServer,IPAddress,IPSubnet,DefaultIPGateway,"
    "DNSServerSearchOrder,DNSDomain,DNSHostName | "
    "ConvertTo-Json -Depth 4 -Compress"
)


class GetIpConfigSkill(Skill):

    name = "network.get_ip_config"

    description = (
        "Retourne la configuration IP active de Windows : "
        "adresses IPv4/IPv6, masque, passerelle, serveurs DNS, "
        "état DHCP et serveur DHCP."
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
                POWERSHELL_COMMAND,
                timeout=POWERSHELL_TIMEOUT_SECONDS,
                execution_policy="Bypass",
            )

        except FileNotFoundError:

            return SkillResult(
                success=False,
                message=(
                    "PowerShell est introuvable sur ce poste."
                ),
            )

        except subprocess.TimeoutExpired:

            return SkillResult(
                success=False,
                message=(
                    "La récupération de la configuration IP "
                    "a dépassé le délai autorisé."
                ),
            )

        except OSError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible d'interroger la configuration "
                    "réseau de Windows."
                ),
                data={
                    "error": str(exc),
                },
            )

        if completed.returncode != 0:

            return SkillResult(
                success=False,
                message=(
                    "Windows n'a pas pu fournir la "
                    "configuration IP."
                ),
                data={
                    "returncode": completed.returncode,
                    "stderr": completed.stderr.strip(),
                },
            )

        raw_output = completed.stdout.strip()

        if not raw_output:

            return SkillResult(
                success=True,
                message=(
                    "Aucune interface réseau avec IP active "
                    "n'a été trouvée."
                ),
                data={
                    "interfaces": [],
                    "count": 0,
                },
            )

        try:

            payload = json.loads(
                raw_output
            )

        except json.JSONDecodeError as exc:

            return SkillResult(
                success=False,
                message=(
                    "La réponse réseau de Windows est invalide."
                ),
                data={
                    "error": str(exc),
                },
            )

        if isinstance(payload, dict):
            interfaces = [payload]
        elif isinstance(payload, list):
            interfaces = payload
        else:
            interfaces = []

        normalized_interfaces = []

        for interface in interfaces:

            if not isinstance(
                interface,
                dict,
            ):
                continue

            normalized_interfaces.append(
                {
                    "description": interface.get(
                        "Description"
                    ),
                    "interface_index": interface.get(
                        "InterfaceIndex"
                    ),
                    "mac_address": interface.get(
                        "MACAddress"
                    ),
                    "dhcp_enabled": interface.get(
                        "DHCPEnabled"
                    ),
                    "dhcp_server": interface.get(
                        "DHCPServer"
                    ),
                    "ip_addresses": self._as_list(
                        interface.get(
                            "IPAddress"
                        )
                    ),
                    "subnets": self._as_list(
                        interface.get(
                            "IPSubnet"
                        )
                    ),
                    "default_gateways": self._as_list(
                        interface.get(
                            "DefaultIPGateway"
                        )
                    ),
                    "dns_servers": self._as_list(
                        interface.get(
                            "DNSServerSearchOrder"
                        )
                    ),
                    "dns_domain": interface.get(
                        "DNSDomain"
                    ),
                    "dns_host_name": interface.get(
                        "DNSHostName"
                    ),
                }
            )

        return SkillResult(
            success=True,
            message=(
                f"Configuration IP récupérée pour "
                f"{len(normalized_interfaces)} interface(s)."
            ),
            data={
                "interfaces": normalized_interfaces,
                "count": len(
                    normalized_interfaces
                ),
            },
        )

    @staticmethod
    def _as_list(
        value: Any,
    ) -> list[Any]:

        if value is None:
            return []

        if isinstance(
            value,
            list,
        ):
            return value

        return [value]
