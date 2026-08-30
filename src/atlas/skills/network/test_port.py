from __future__ import annotations

import ipaddress
import re
import socket
import time
from typing import Any

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


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

DEFAULT_TIMEOUT_SECONDS = 3.0
MIN_TIMEOUT_SECONDS = 0.25
MAX_TIMEOUT_SECONDS = 10.0


class TestPortNetworkSkill(Skill):

    name = "network.test_port"

    description = (
        "Teste si un port TCP précis est accessible sur une adresse IP "
        "ou un nom d'hôte."
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
            "port": {
                "type": "integer",
                "minimum": 1,
                "maximum": 65535,
                "description": (
                    "Port TCP à tester."
                ),
            },
            "timeout_seconds": {
                "type": "number",
                "minimum": MIN_TIMEOUT_SECONDS,
                "maximum": MAX_TIMEOUT_SECONDS,
                "default": DEFAULT_TIMEOUT_SECONDS,
                "description": (
                    "Délai maximal de connexion en secondes."
                ),
            },
        },
        "required": [
            "target",
            "port",
        ],
        "additionalProperties": False,
    }

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    def execute(
        self,
        target: str,
        port: int,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
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
            not isinstance(port, int)
            or isinstance(port, bool)
            or port < 1
            or port > 65535
        ):

            return SkillResult(
                success=False,
                message=(
                    "Le port TCP doit être compris entre 1 et 65535."
                ),
            )

        if (
            not isinstance(
                timeout_seconds,
                (int, float),
            )
            or isinstance(
                timeout_seconds,
                bool,
            )
        ):

            return SkillResult(
                success=False,
                message=(
                    "Le délai de connexion est invalide."
                ),
            )

        timeout_value = float(
            timeout_seconds
        )

        if (
            timeout_value < MIN_TIMEOUT_SECONDS
            or timeout_value > MAX_TIMEOUT_SECONDS
        ):

            return SkillResult(
                success=False,
                message=(
                    "Le délai de connexion doit être compris entre "
                    "0,25 et 10 secondes."
                ),
            )

        started_at = time.perf_counter()

        try:

            connection = socket.create_connection(
                (
                    normalized_target,
                    port,
                ),
                timeout=timeout_value,
            )

        except socket.timeout:

            elapsed_ms = round(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000,
                2,
            )

            return SkillResult(
                success=True,
                message=(
                    f"Le port TCP {port} de '{normalized_target}' "
                    "ne répond pas dans le délai imparti."
                ),
                data={
                    "target": normalized_target,
                    "port": port,
                    "protocol": "tcp",
                    "open": False,
                    "status": "timeout",
                    "elapsed_ms": elapsed_ms,
                    "timeout_seconds": timeout_value,
                },
            )

        except ConnectionRefusedError:

            elapsed_ms = round(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000,
                2,
            )

            return SkillResult(
                success=True,
                message=(
                    f"Le port TCP {port} de '{normalized_target}' "
                    "est fermé ou refuse les connexions."
                ),
                data={
                    "target": normalized_target,
                    "port": port,
                    "protocol": "tcp",
                    "open": False,
                    "status": "refused",
                    "elapsed_ms": elapsed_ms,
                    "timeout_seconds": timeout_value,
                },
            )

        except socket.gaierror as exc:

            return SkillResult(
                success=False,
                message=(
                    f"Impossible de résoudre la cible "
                    f"'{normalized_target}'."
                ),
                data={
                    "target": normalized_target,
                    "port": port,
                    "protocol": "tcp",
                    "error": str(exc),
                },
            )

        except OSError as exc:

            elapsed_ms = round(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000,
                2,
            )

            return SkillResult(
                success=True,
                message=(
                    f"Le port TCP {port} de '{normalized_target}' "
                    "n'est pas accessible."
                ),
                data={
                    "target": normalized_target,
                    "port": port,
                    "protocol": "tcp",
                    "open": False,
                    "status": "unreachable",
                    "elapsed_ms": elapsed_ms,
                    "timeout_seconds": timeout_value,
                    "error": str(exc),
                },
            )

        else:

            elapsed_ms = round(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000,
                2,
            )

            try:

                peer = connection.getpeername()

            finally:

                connection.close()

            peer_address = (
                peer[0]
                if isinstance(peer, tuple)
                and peer
                else None
            )

            return SkillResult(
                success=True,
                message=(
                    f"Le port TCP {port} de '{normalized_target}' "
                    "est accessible."
                ),
                data={
                    "target": normalized_target,
                    "resolved_address": peer_address,
                    "port": port,
                    "protocol": "tcp",
                    "open": True,
                    "status": "open",
                    "elapsed_ms": elapsed_ms,
                    "timeout_seconds": timeout_value,
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
