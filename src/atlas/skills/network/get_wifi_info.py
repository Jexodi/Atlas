from __future__ import annotations

import re
import subprocess
from typing import Any

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


NETSH_TIMEOUT_SECONDS = 10.0


class GetWifiInfoNetworkSkill(Skill):

    name = "network.get_wifi_info"

    description = (
        "Récupère les informations de la connexion Wi-Fi active, "
        "notamment SSID, BSSID, signal, canal, radio et débits."
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
                    "interfaces",
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
                    "La récupération des informations Wi-Fi "
                    "a dépassé le délai autorisé."
                ),
            )

        except OSError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible de récupérer les informations Wi-Fi."
                ),
                data={
                    "error": str(exc),
                },
            )

        if completed.returncode != 0:

            return SkillResult(
                success=False,
                message=(
                    "Windows n'a pas pu retourner les informations Wi-Fi."
                ),
                data={
                    "returncode": completed.returncode,
                    "stdout": completed.stdout.strip(),
                    "stderr": completed.stderr.strip(),
                },
            )

        raw_output = completed.stdout.strip()

        interfaces = self._parse_interfaces(
            raw_output
        )

        connected = [
            interface
            for interface in interfaces
            if interface.get(
                "state",
                ""
            ).casefold() in {
                "connected",
                "connecté",
                "connectee",
                "connectée",
            }
        ]

        if not interfaces:

            return SkillResult(
                success=True,
                message=(
                    "Aucune interface Wi-Fi n'a été détectée."
                ),
                data={
                    "interfaces": [],
                    "connected_interfaces": [],
                    "count": 0,
                    "connected_count": 0,
                },
            )

        if connected:

            message = (
                f"{len(interfaces)} interface(s) Wi-Fi détectée(s), "
                f"dont {len(connected)} connectée(s)."
            )

        else:

            message = (
                f"{len(interfaces)} interface(s) Wi-Fi détectée(s), "
                "mais aucune connexion Wi-Fi active."
            )

        return SkillResult(
            success=True,
            message=message,
            data={
                "interfaces": interfaces,
                "connected_interfaces": connected,
                "count": len(interfaces),
                "connected_count": len(
                    connected
                ),
                "raw": raw_output,
            },
        )

    def _parse_interfaces(
        self,
        raw_output: str,
    ) -> list[dict[str, Any]]:

        interfaces: list[
            dict[str, Any]
        ] = []

        current: dict[str, Any] = {}

        for raw_line in raw_output.splitlines():

            line = raw_line.strip()

            if not line:
                continue

            if ":" not in line:
                continue

            key, value = line.split(
                ":",
                1,
            )

            normalized_key = (
                self._normalize_key(
                    key
                )
            )

            normalized_value = (
                value.strip()
            )

            if normalized_key == "name":

                if current:
                    interfaces.append(
                        current
                    )

                current = {
                    "name": normalized_value,
                }

                continue

            if not current:
                continue

            mapping = {
                "description": "description",
                "guid": "guid",
                "physical_address": "physical_address",
                "state": "state",
                "ssid": "ssid",
                "bssid": "bssid",
                "network_type": "network_type",
                "radio_type": "radio_type",
                "authentication": "authentication",
                "cipher": "cipher",
                "connection_mode": "connection_mode",
                "channel": "channel",
                "receive_rate": "receive_rate_mbps",
                "transmit_rate": "transmit_rate_mbps",
                "signal": "signal_percent",
                "profile": "profile",
            }

            destination_key = mapping.get(
                normalized_key
            )

            if destination_key is None:
                continue

            if destination_key == "channel":

                current[
                    destination_key
                ] = self._parse_int(
                    normalized_value
                )

            elif destination_key in {
                "receive_rate_mbps",
                "transmit_rate_mbps",
            }:

                current[
                    destination_key
                ] = self._parse_float(
                    normalized_value
                )

            elif destination_key == "signal_percent":

                current[
                    destination_key
                ] = self._parse_percent(
                    normalized_value
                )

            else:

                current[
                    destination_key
                ] = normalized_value

        if current:

            interfaces.append(
                current
            )

        return interfaces

    @staticmethod
    def _normalize_key(
        value: str,
    ) -> str:

        key = value.strip().casefold()

        replacements = {
            "nom": "name",
            "name": "name",
            "description": "description",
            "guid": "guid",
            "adresse physique": "physical_address",
            "physical address": "physical_address",
            "état": "state",
            "etat": "state",
            "state": "state",
            "ssid": "ssid",
            "bssid": "bssid",
            "type de réseau": "network_type",
            "network type": "network_type",
            "type de radio": "radio_type",
            "radio type": "radio_type",
            "authentification": "authentication",
            "authentication": "authentication",
            "chiffrement": "cipher",
            "cipher": "cipher",
            "mode de connexion": "connection_mode",
            "connection mode": "connection_mode",
            "canal": "channel",
            "channel": "channel",
            "débit de réception (mbits/s)": "receive_rate",
            "debit de reception (mbits/s)": "receive_rate",
            "receive rate (mbps)": "receive_rate",
            "débit de transmission (mbits/s)": "transmit_rate",
            "debit de transmission (mbits/s)": "transmit_rate",
            "transmit rate (mbps)": "transmit_rate",
            "signal": "signal",
            "profil": "profile",
            "profile": "profile",
        }

        return replacements.get(
            key,
            key,
        )

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
    def _parse_float(
        value: str,
    ) -> float | None:

        normalized = (
            value.replace(
                ",",
                ".",
            )
        )

        match = re.search(
            r"-?\d+(?:\.\d+)?",
            normalized,
        )

        if not match:
            return None

        try:
            return float(
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
