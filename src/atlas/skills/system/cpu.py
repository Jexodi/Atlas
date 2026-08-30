import psutil

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class GetCpuUsageSkill(Skill):

    name = "system.get_cpu_usage"

    description = "Retourne l'utilisation globale du processeur."

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    def execute(
        self,
        **kwargs,
    ) -> SkillResult:

        usage = psutil.cpu_percent(
            interval=0.5
        )

        logical_cpu_count = psutil.cpu_count(
            logical=True
        )

        physical_cpu_count = psutil.cpu_count(
            logical=False
        )

        return SkillResult(
            success=True,
            message=f"CPU utilisé à {usage} %.",
            data={
                "usage_percent": usage,
                "logical_cores": logical_cpu_count,
                "physical_cores": physical_cpu_count,
            },
        )