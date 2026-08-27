import psutil

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class GetSystemStatusSkill(Skill):

    name = "system.get_status"

    description = "Retourne un résumé de l'état du système."

    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    def execute(
        self,
        **kwargs,
    ) -> SkillResult:

        cpu_usage = psutil.cpu_percent(
            interval=0.5
        )

        memory = psutil.virtual_memory()

        boot_time = psutil.boot_time()

        network = psutil.net_io_counters()

        return SkillResult(
            success=True,
            message="État système récupéré.",
            data={
                "cpu": {
                    "usage_percent": cpu_usage,
                },
                "memory": {
                    "usage_percent": memory.percent,
                    "available_gb": round(
                        memory.available / (1024 ** 3),
                        2,
                    ),
                },
                "system": {
                    "boot_timestamp": boot_time,
                },
                "network": {
                    "bytes_sent": network.bytes_sent,
                    "bytes_received": network.bytes_recv,
                },
            },
        )