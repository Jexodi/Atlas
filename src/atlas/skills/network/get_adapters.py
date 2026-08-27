from __future__ import annotations

import socket

import psutil

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class GetNetworkAdaptersSkill(Skill):

    name = "network.get_adapters"

    description = (
        "Liste les cartes réseau Windows et retourne "
        "leur état, leurs adresses IP, leur adresse MAC, "
        "leur vitesse et leur MTU."
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
        **kwargs,
    ) -> SkillResult:

        try:

            addresses = psutil.net_if_addrs()
            stats = psutil.net_if_stats()

        except Exception as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible de récupérer "
                    "les cartes réseau."
                ),
                data={
                    "error": str(exc),
                },
            )

        adapters = []

        for adapter_name in sorted(
            set(addresses) | set(stats),
            key=str.casefold,
        ):

            adapter_addresses = addresses.get(
                adapter_name,
                [],
            )

            adapter_stats = stats.get(
                adapter_name
            )

            ipv4_addresses = []
            ipv6_addresses = []
            mac_addresses = []

            for address in adapter_addresses:

                if address.family == socket.AF_INET:

                    ipv4_addresses.append(
                        {
                            "address": address.address,
                            "netmask": address.netmask,
                            "broadcast": address.broadcast,
                        }
                    )

                    continue

                if address.family == socket.AF_INET6:

                    ipv6_addresses.append(
                        {
                            "address": address.address,
                            "netmask": address.netmask,
                        }
                    )

                    continue

                if address.family == psutil.AF_LINK:

                    if address.address:
                        mac_addresses.append(
                            address.address
                        )

            adapters.append(
                {
                    "name": adapter_name,
                    "is_up": (
                        adapter_stats.isup
                        if adapter_stats is not None
                        else None
                    ),
                    "speed_mbps": (
                        adapter_stats.speed
                        if adapter_stats is not None
                        else None
                    ),
                    "mtu": (
                        adapter_stats.mtu
                        if adapter_stats is not None
                        else None
                    ),
                    "mac_addresses": mac_addresses,
                    "ipv4_addresses": ipv4_addresses,
                    "ipv6_addresses": ipv6_addresses,
                }
            )

        if not adapters:

            return SkillResult(
                success=False,
                message=(
                    "Aucune carte réseau n'a été trouvée."
                ),
                data={
                    "adapters": [],
                },
            )

        active_count = sum(
            1
            for adapter in adapters
            if adapter["is_up"] is True
        )

        return SkillResult(
            success=True,
            message=(
                f"{len(adapters)} carte(s) réseau trouvée(s), "
                f"dont {active_count} active(s)."
            ),
            data={
                "adapters": adapters,
                "count": len(adapters),
                "active_count": active_count,
            },
        )
