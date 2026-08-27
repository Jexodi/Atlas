from __future__ import annotations

import ipaddress
import re
import socket
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


class DnsLookupSkill(Skill):

    name = "network.dns_lookup"

    description = (
        "Résout un nom d'hôte en adresses IP ou effectue "
        "une résolution DNS inverse d'une adresse IP."
    )

    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": (
                    "Nom d'hôte, adresse IPv4 ou adresse IPv6 à résoudre."
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
        **kwargs: Any,
    ) -> SkillResult:

        normalized_target = self._validate_target(
            target
        )

        if normalized_target is None:

            return SkillResult(
                success=False,
                message=(
                    "La cible DNS fournie est invalide."
                ),
            )

        try:

            ip_value = ipaddress.ip_address(
                normalized_target
            )

        except ValueError:

            return self._forward_lookup(
                normalized_target
            )

        return self._reverse_lookup(
            str(ip_value)
        )

    def _forward_lookup(
        self,
        hostname: str,
    ) -> SkillResult:

        try:

            results = socket.getaddrinfo(
                hostname,
                None,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )

        except socket.gaierror as exc:

            return SkillResult(
                success=False,
                message=(
                    f"Impossible de résoudre le nom d'hôte "
                    f"'{hostname}'."
                ),
                data={
                    "target": hostname,
                    "lookup_type": "forward",
                    "error": str(exc),
                },
            )

        addresses: list[str] = []

        for result in results:

            sockaddr = result[4]

            if not sockaddr:
                continue

            address = sockaddr[0]

            if address not in addresses:
                addresses.append(
                    address
                )

        if not addresses:

            return SkillResult(
                success=False,
                message=(
                    f"Aucune adresse IP n'a été trouvée "
                    f"pour '{hostname}'."
                ),
                data={
                    "target": hostname,
                    "lookup_type": "forward",
                },
            )

        ipv4 = []
        ipv6 = []

        for address in addresses:

            try:

                parsed = ipaddress.ip_address(
                    address
                )

            except ValueError:
                continue

            if parsed.version == 4:
                ipv4.append(
                    address
                )
            else:
                ipv6.append(
                    address
                )

        return SkillResult(
            success=True,
            message=(
                f"Résolution DNS de '{hostname}' effectuée."
            ),
            data={
                "target": hostname,
                "lookup_type": "forward",
                "addresses": addresses,
                "ipv4": ipv4,
                "ipv6": ipv6,
            },
        )

    def _reverse_lookup(
        self,
        address: str,
    ) -> SkillResult:

        try:

            hostname, aliases, addresses = (
                socket.gethostbyaddr(
                    address
                )
            )

        except (
            socket.herror,
            socket.gaierror,
        ) as exc:

            return SkillResult(
                success=False,
                message=(
                    f"Aucun nom DNS inverse n'a été trouvé "
                    f"pour '{address}'."
                ),
                data={
                    "target": address,
                    "lookup_type": "reverse",
                    "error": str(exc),
                },
            )

        return SkillResult(
            success=True,
            message=(
                f"Résolution DNS inverse de '{address}' effectuée."
            ),
            data={
                "target": address,
                "lookup_type": "reverse",
                "hostname": hostname,
                "aliases": aliases,
                "addresses": addresses,
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
