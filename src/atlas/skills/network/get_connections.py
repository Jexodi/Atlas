from __future__ import annotations

from typing import Any

import psutil

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


MAX_CONNECTIONS = 500


class GetConnectionsNetworkSkill(Skill):

    name = "network.get_connections"

    description = (
        "Liste les connexions réseau TCP et UDP actives de Windows "
        "avec les processus associés lorsque l'information est disponible."
    )

    parameters = {
        "type": "object",
        "properties": {
            "protocol": {
                "type": "string",
                "enum": [
                    "all",
                    "tcp",
                    "udp",
                ],
                "default": "all",
                "description": (
                    "Filtre les connexions par protocole."
                ),
            },
            "state": {
                "type": "string",
                "default": "all",
                "description": (
                    "Filtre optionnel sur l'état TCP, par exemple "
                    "ESTABLISHED ou LISTEN."
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
        protocol: str = "all",
        state: str = "all",
        **kwargs: Any,
    ) -> SkillResult:

        if not isinstance(
            protocol,
            str,
        ):

            return SkillResult(
                success=False,
                message=(
                    "Le protocole demandé est invalide."
                ),
            )

        protocol_value = protocol.strip().lower()

        if protocol_value not in {
            "all",
            "tcp",
            "udp",
        }:

            return SkillResult(
                success=False,
                message=(
                    "Le protocole doit être 'all', 'tcp' ou 'udp'."
                ),
            )

        if not isinstance(
            state,
            str,
        ):

            return SkillResult(
                success=False,
                message=(
                    "L'état réseau demandé est invalide."
                ),
            )

        state_value = state.strip().upper()

        if not state_value:
            state_value = "ALL"

        try:

            connections = psutil.net_connections(
                kind="inet"
            )

        except psutil.AccessDenied:

            return SkillResult(
                success=False,
                message=(
                    "Windows a refusé l'accès à la liste "
                    "complète des connexions réseau."
                ),
            )

        except OSError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible de récupérer les connexions réseau."
                ),
                data={
                    "error": str(exc),
                },
            )

        results = []

        for connection in connections:

            connection_protocol = (
                "tcp"
                if connection.type == 1
                else "udp"
            )

            if (
                protocol_value != "all"
                and connection_protocol
                != protocol_value
            ):

                continue

            status = (
                connection.status
                if connection.status
                else "NONE"
            )

            if (
                state_value != "ALL"
                and status.upper()
                != state_value
            ):

                continue

            local_address = None
            local_port = None

            if connection.laddr:

                local_address = (
                    connection.laddr.ip
                )

                local_port = (
                    connection.laddr.port
                )

            remote_address = None
            remote_port = None

            if connection.raddr:

                remote_address = (
                    connection.raddr.ip
                )

                remote_port = (
                    connection.raddr.port
                )

            process_name = None

            if connection.pid is not None:

                try:

                    process_name = (
                        psutil.Process(
                            connection.pid
                        ).name()
                    )

                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):

                    process_name = None

            results.append(
                {
                    "protocol": (
                        connection_protocol
                    ),
                    "status": status,
                    "local_address": (
                        local_address
                    ),
                    "local_port": local_port,
                    "remote_address": (
                        remote_address
                    ),
                    "remote_port": remote_port,
                    "pid": connection.pid,
                    "process_name": (
                        process_name
                    ),
                }
            )

            if len(results) >= MAX_CONNECTIONS:
                break

        established_count = sum(
            1
            for item in results
            if item["status"].upper()
            == "ESTABLISHED"
        )

        listen_count = sum(
            1
            for item in results
            if item["status"].upper()
            == "LISTEN"
        )

        return SkillResult(
            success=True,
            message=(
                f"{len(results)} connexion(s) réseau récupérée(s), "
                f"dont {established_count} établie(s) et "
                f"{listen_count} en écoute."
            ),
            data={
                "connections": results,
                "count": len(results),
                "established_count": (
                    established_count
                ),
                "listen_count": (
                    listen_count
                ),
                "protocol_filter": (
                    protocol_value
                ),
                "state_filter": (
                    state_value
                ),
                "truncated": (
                    len(results)
                    >= MAX_CONNECTIONS
                ),
            },
        )
