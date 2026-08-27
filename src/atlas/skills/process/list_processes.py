import subprocess

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class ListProcessesSkill(Skill):

    name = "process.list"

    description = "Liste les processus Windows actifs."

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    def execute(
        self,
        **kwargs,
    ) -> SkillResult:

        completed = subprocess.run(
            [
                "tasklist",
                "/FO",
                "CSV",
                "/NH",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if completed.returncode != 0:

            return SkillResult(
                success=False,
                message=(
                    completed.stderr.strip()
                    or "Impossible de récupérer la liste des processus."
                ),
            )

        return SkillResult(
            success=True,
            message="Liste des processus récupérée.",
            data={
                "raw": completed.stdout,
            },
        )