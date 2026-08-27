import psutil

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class GetMemoryUsageSkill(Skill):

    name = "system.get_memory_usage"

    description = "Retourne l'utilisation de la mémoire vive."

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    def execute(
        self,
        **kwargs,
    ) -> SkillResult:

        memory = psutil.virtual_memory()

        gb = 1024 ** 3

        total = round(
            memory.total / gb,
            2,
        )

        available = round(
            memory.available / gb,
            2,
        )

        used = round(
            memory.used / gb,
            2,
        )

        return SkillResult(
            success=True,
            message=(
                f"RAM utilisée à {memory.percent} %."
            ),
            data={
                "usage_percent": memory.percent,
                "total_gb": total,
                "used_gb": used,
                "available_gb": available,
            },
        )