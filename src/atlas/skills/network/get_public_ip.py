from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.request
from typing import Any

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


PUBLIC_IP_URL = (
    "https://api64.ipify.org?format=json"
)

REQUEST_TIMEOUT_SECONDS = 5.0


class GetPublicIpNetworkSkill(Skill):

    name = "network.get_public_ip"

    description = (
        "Récupère l'adresse IP publique actuellement utilisée "
        "pour accéder à Internet."
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

        request = urllib.request.Request(
            PUBLIC_IP_URL,
            headers={
                "Accept": "application/json",
                "User-Agent": "AtlasV2/1.0",
            },
            method="GET",
        )

        try:

            with urllib.request.urlopen(
                request,
                timeout=REQUEST_TIMEOUT_SECONDS,
            ) as response:

                status_code = getattr(
                    response,
                    "status",
                    200,
                )

                payload = response.read(
                    4096
                )

        except urllib.error.HTTPError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Le service de détection de l'adresse IP publique "
                    "a refusé la requête."
                ),
                data={
                    "status_code": exc.code,
                },
            )

        except urllib.error.URLError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible de joindre le service de détection "
                    "de l'adresse IP publique."
                ),
                data={
                    "error": str(
                        exc.reason
                    ),
                },
            )

        except TimeoutError:

            return SkillResult(
                success=False,
                message=(
                    "La récupération de l'adresse IP publique "
                    "a dépassé le délai autorisé."
                ),
            )

        except OSError as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible de récupérer l'adresse IP publique."
                ),
                data={
                    "error": str(exc),
                },
            )

        if status_code != 200:

            return SkillResult(
                success=False,
                message=(
                    "Le service de détection de l'adresse IP publique "
                    "a renvoyé une réponse inattendue."
                ),
                data={
                    "status_code": status_code,
                },
            )

        try:

            decoded = json.loads(
                payload.decode(
                    "utf-8"
                )
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):

            return SkillResult(
                success=False,
                message=(
                    "La réponse du service d'adresse IP publique "
                    "est invalide."
                ),
            )

        public_ip = decoded.get(
            "ip"
        )

        if not isinstance(
            public_ip,
            str,
        ):

            return SkillResult(
                success=False,
                message=(
                    "Le service n'a renvoyé aucune adresse IP publique valide."
                ),
            )

        public_ip = public_ip.strip()

        try:

            parsed_ip = ipaddress.ip_address(
                public_ip
            )

        except ValueError:

            return SkillResult(
                success=False,
                message=(
                    "Le service a renvoyé une adresse IP publique invalide."
                ),
            )

        return SkillResult(
            success=True,
            message=(
                f"L'adresse IP publique actuelle est {parsed_ip}."
            ),
            data={
                "public_ip": str(
                    parsed_ip
                ),
                "version": parsed_ip.version,
                "service": "ipify",
            },
        )
