from __future__ import annotations

import ipaddress
import re
import subprocess
from typing import Any

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


TRACEROUTE_TIMEOUT_SECONDS = 45.0

HOSTNAME_PATTERN = re.compile(
    r"^(?=.{1,253}$)"
    r"(?:"
    r"[A-Za-z0-9]"
    r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"\."
    r")*"
    r"[A-Za-z0-9]"
    r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"\.?$"
)


class TracerouteNetworkSkill(Skill):

    name = "network.traceroute"

    description = (
        "Trace le chemin réseau vers une adresse IP ou un nom d'hôte "
        "avec tracert sous Windows."
    )

    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": (
                    "Adresse IPv4, IPv6 ou nom d'hôte à tracer."
                ),
            },
            "max_hops": {
                "type": "integer",
                "minimum": 1,
                "maximum": 30,
                "default": 20,
                "description": (
                    "Nombre maximal de sauts réseau à explorer."
                ),
            },
            "timeout_ms": {
                "type": "integer",
                "minimum": 250,
                "maximum": 5000,
                "default": 1500,
                "description": (
                    "Délai maximal d'attente par réponse en millisecondes."
                ),
            },
        },
        "required": [
            "target",
        ],
        "additionalProperties": False,
    }

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    def execute(
        self,
        target: str,
        max_hops: int = 20,
        timeout_ms: int = 1500,
        **kwargs: Any,
    ) -> SkillResult:

        normalized_target = self._validate_target(
            target
        )

        if normalized_target is None:

            return SkillResult(
                success=False,
                message=(
                    "La cible réseau fournie est invalide."
                ),
            )

        if (
            not isinstance(max_hops, int)
            or isinstance(max_hops, bool)
            or max_hops < 1
            or max_hops > 30
        ):

            return SkillResult(
                success=False,
                message=(
                    "Le nombre maximal de sauts doit être compris "
                    "entre 1 et 30."
                ),
            )

        if (
            not isinstance(timeout_ms, int)
            or isinstance(timeout_ms, bool)
            or timeout_ms < 250
            or timeout_ms > 5000
        ):

            return SkillResult(
                success=False,
                message=(
                    "Le délai traceroute doit être compris entre "
                    "250 et 5000 millisecondes."
                ),
            )

        try:

            completed = subprocess.run(
                [
                    "tracert.exe",
                    "-d",
                    "-h",
                    str(max_hops),
                    "-w",
                    str(timeout_ms),
                    normalized_target,
                ],
                capture_output=True,
                text=True,
                timeout=TRACEROUTE_TIMEOUT_SECONDS,
                shell=False,
                check=False,
            )

        except FileNotFoundError:

            return SkillResult(
                success=False,
                message=(
                    "La commande tracert de Windows est introuvable."
                ),
            )

        except subprocess.TimeoutExpired:

            return SkillResult(
                success=False,
                message=(
                    "Le traceroute a dépassé le délai maximal autorisé."
                ),
                data={
                    "target": normalized_target,
                },
            )

        except OSError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible d'exécuter le traceroute."
                ),
                data={
                    "target": normalized_target,
                    "error": str(exc),
                },
            )

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()

        return SkillResult(
            success=(
                completed.returncode == 0
            ),
            message=(
                f"Traceroute vers '{normalized_target}' terminé."
                if completed.returncode == 0
                else (
                    f"Le traceroute vers '{normalized_target}' "
                    "n'a pas pu se terminer correctement."
                )
            ),
            data={
                "target": normalized_target,
                "max_hops": max_hops,
                "timeout_ms": timeout_ms,
                "returncode": completed.returncode,
                "raw": stdout,
                "stderr": stderr,
            },
        )

    @staticmethod
    def _validate_target(
        value: Any,
    ) -> str | None:

        if not isinstance(
            value,
            str,
        ):

            return None

        target = value.strip()

        if not target:
            return None

        if len(target) > 253:
            return None

        try:

            ipaddress.ip_address(
                target
            )

            return target

        except ValueError:
            pass

        if HOSTNAME_PATTERN.fullmatch(
            target
        ):

            return target.rstrip(".")

        return None
