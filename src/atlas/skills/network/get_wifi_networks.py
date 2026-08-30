from __future__ import annotations

import re
import subprocess
from typing import Any

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


NETSH_TIMEOUT_SECONDS = 15.0
MAX_NETWORKS = 100


class GetWifiNetworksNetworkSkill(Skill):

    name = "network.get_wifi_networks"

    description = (
        "Liste les réseaux Wi-Fi visibles autour du poste sans s'y connecter."
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

            completed = subprocess.run(
                [
                    "netsh.exe",
                    "wlan",
                    "show",
                    "networks",
                    "mode=bssid",
                ],
                capture_output=True,
                text=True,
                timeout=NETSH_TIMEOUT_SECONDS,
                shell=False,
                check=False,
            )

        except FileNotFoundError:

            return SkillResult(
                success=False,
                message=(
                    "La commande netsh de Windows est introuvable."
                ),
            )

        except subprocess.TimeoutExpired:

            return SkillResult(
                success=False,
                message=(
                    "La recherche des réseaux Wi-Fi "
                    "a dépassé le délai autorisé."
                ),
            )

        except OSError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible de rechercher les réseaux Wi-Fi."
                ),
                data={
                    "error": str(exc),
                },
            )

        if completed.returncode != 0:

            return SkillResult(
                success=False,
                message=(
                    "Windows n'a pas pu retourner les réseaux Wi-Fi visibles."
                ),
                data={
                    "returncode": completed.returncode,
                    "stdout": completed.stdout.strip(),
                    "stderr": completed.stderr.strip(),
                },
            )

        raw_output = completed.stdout.strip()

        networks = self._parse_networks(
            raw_output
        )

        truncated = (
            len(networks)
            > MAX_NETWORKS
        )

        if truncated:

            networks = networks[
                :MAX_NETWORKS
            ]

        if not networks:

            return SkillResult(
                success=True,
                message=(
                    "Aucun réseau Wi-Fi visible n'a été détecté."
                ),
                data={
                    "networks": [],
                    "count": 0,
                    "truncated": False,
                    "raw": raw_output,
                },
            )

        return SkillResult(
            success=True,
            message=(
                f"{len(networks)} réseau(x) Wi-Fi visible(s) détecté(s)."
            ),
            data={
                "networks": networks,
                "count": len(networks),
                "truncated": truncated,
                "max_networks": MAX_NETWORKS,
                "raw": raw_output,
            },
        )

    def _parse_networks(
        self,
        raw_output: str,
    ) -> list[dict[str, Any]]:

        networks: list[
            dict[str, Any]
        ] = []

        current_network: dict[
            str,
            Any
        ] | None = None

        current_bssid: dict[
            str,
            Any
        ] | None = None

        for raw_line in raw_output.splitlines():

            line = raw_line.strip()

            if not line:
                continue

            ssid_match = re.match(
                r"^SSID\s+\d+\s*:\s*(.*)$",
                line,
                flags=re.IGNORECASE,
            )

            if ssid_match:

                if current_network is not None:

                    if current_bssid is not None:

                        current_network.setdefault(
                            "access_points",
                            [],
                        ).append(
                            current_bssid
                        )

                        current_bssid = None

                    networks.append(
                        current_network
                    )

                current_network = {
                    "ssid": (
                        ssid_match.group(1).strip()
                    ),
                    "access_points": [],
                }

                continue

            if current_network is None:
                continue

            bssid_match = re.match(
                r"^BSSID\s+\d+\s*:\s*(.*)$",
                line,
                flags=re.IGNORECASE,
            )

            if bssid_match:

                if current_bssid is not None:

                    current_network[
                        "access_points"
                    ].append(
                        current_bssid
                    )

                current_bssid = {
                    "bssid": (
                        bssid_match.group(1).strip()
                    ),
                }

                continue

            if ":" not in line:
                continue

            key, value = line.split(
                ":",
                1,
            )

            key = key.strip().casefold()
            value = value.strip()

            network_key_map = {
                "type de réseau": "network_type",
                "network type": "network_type",
                "authentification": "authentication",
                "authentication": "authentication",
                "chiffrement": "encryption",
                "encryption": "encryption",
            }

            bssid_key_map = {
                "signal": "signal_percent",
                "type de radio": "radio_type",
                "radio type": "radio_type",
                "canal": "channel",
                "channel": "channel",
            }

            if key in network_key_map:

                current_network[
                    network_key_map[key]
                ] = value

                continue

            if (
                current_bssid is not None
                and key in bssid_key_map
            ):

                destination_key = (
                    bssid_key_map[key]
                )

                if destination_key == "signal_percent":

                    current_bssid[
                        destination_key
                    ] = self._parse_percent(
                        value
                    )

                elif destination_key == "channel":

                    current_bssid[
                        destination_key
                    ] = self._parse_int(
                        value
                    )

                else:

                    current_bssid[
                        destination_key
                    ] = value

        if current_network is not None:

            if current_bssid is not None:

                current_network.setdefault(
                    "access_points",
                    [],
                ).append(
                    current_bssid
                )

            networks.append(
                current_network
            )

        for network in networks:

            access_points = network.get(
                "access_points",
                [],
            )

            signals = [
                ap.get(
                    "signal_percent"
                )
                for ap in access_points
                if isinstance(
                    ap.get(
                        "signal_percent"
                    ),
                    int,
                )
            ]

            network[
                "best_signal_percent"
            ] = (
                max(signals)
                if signals
                else None
            )

            network[
                "access_point_count"
            ] = len(
                access_points
            )

        networks.sort(
            key=lambda item: (
                item.get(
                    "best_signal_percent"
                )
                if isinstance(
                    item.get(
                        "best_signal_percent"
                    ),
                    int,
                )
                else -1
            ),
            reverse=True,
        )

        return networks

    @staticmethod
    def _parse_int(
        value: str,
    ) -> int | None:

        match = re.search(
            r"-?\d+",
            value,
        )

        if not match:
            return None

        try:

            return int(
                match.group(0)
            )

        except ValueError:

            return None

    @staticmethod
    def _parse_percent(
        value: str,
    ) -> int | None:

        match = re.search(
            r"(\d{1,3})\s*%",
            value,
        )

        if not match:
            return None

        try:

            percent = int(
                match.group(1)
            )

        except ValueError:

            return None

        return max(
            0,
            min(
                100,
                percent,
            ),
        )
