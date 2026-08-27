from __future__ import annotations

import ipaddress
import re
import subprocess
from typing import Any

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


PING_TIMEOUT_SECONDS = 20.0

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


class PingNetworkSkill(Skill):

    name = "network.ping"

    description = (
        "Teste l'accessibilité réseau d'une adresse IP ou d'un nom "
        "d'hôte avec la commande ping Windows."
    )

    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": (
                    "Adresse IPv4, IPv6 ou nom d'hôte à tester."
                ),
            },
            "count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "default": 4,
                "description": (
                    "Nombre de requêtes ICMP à envoyer."
                ),
            },
            "timeout_ms": {
                "type": "integer",
                "minimum": 250,
                "maximum": 10000,
                "default": 2000,
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
        count: int = 4,
        timeout_ms: int = 2000,
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
            not isinstance(count, int)
            or isinstance(count, bool)
            or count < 1
            or count > 10
        ):

            return SkillResult(
                success=False,
                message=(
                    "Le nombre de requêtes ping doit être "
                    "compris entre 1 et 10."
                ),
            )

        if (
            not isinstance(timeout_ms, int)
            or isinstance(timeout_ms, bool)
            or timeout_ms < 250
            or timeout_ms > 10000
        ):

            return SkillResult(
                success=False,
                message=(
                    "Le délai ping doit être compris entre "
                    "250 et 10000 millisecondes."
                ),
            )

        try:

            completed = subprocess.run(
                [
                    "ping.exe",
                    "-n",
                    str(count),
                    "-w",
                    str(timeout_ms),
                    normalized_target,
                ],
                capture_output=True,
                text=True,
                timeout=PING_TIMEOUT_SECONDS,
                shell=False,
                check=False,
            )

        except FileNotFoundError:

            return SkillResult(
                success=False,
                message=(
                    "La commande ping de Windows est introuvable."
                ),
            )

        except subprocess.TimeoutExpired:

            return SkillResult(
                success=False,
                message=(
                    "Le test ping a dépassé le délai maximal autorisé."
                ),
                data={
                    "target": normalized_target,
                },
            )

        except OSError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible d'exécuter le test ping."
                ),
                data={
                    "target": normalized_target,
                    "error": str(exc),
                },
            )

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()

        reachable = (
            completed.returncode == 0
        )

        if reachable:

            message = (
                f"La cible '{normalized_target}' répond au ping."
            )
        else:

            message = (
                f"La cible '{normalized_target}' ne répond pas au ping."
            )

        return SkillResult(
            success=True,
            message=message,
            data={
                "target": normalized_target,
                "reachable": reachable,
                "count": count,
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
