import psutil

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class GetDiskUsageSkill(Skill):

    name = "system.get_disk_usage"

    description = "Retourne l'utilisation des disques locaux."

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    def execute(
        self,
        **kwargs,
    ) -> SkillResult:

        disks = []

        for partition in psutil.disk_partitions(
            all=False
        ):

            try:

                usage = psutil.disk_usage(
                    partition.mountpoint
                )

            except (
                PermissionError,
                OSError,
            ):
                continue

            gb = 1024 ** 3

            disks.append(
                {
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "filesystem": partition.fstype,
                    "total_gb": round(
                        usage.total / gb,
                        2,
                    ),
                    "used_gb": round(
                        usage.used / gb,
                        2,
                    ),
                    "free_gb": round(
                        usage.free / gb,
                        2,
                    ),
                    "usage_percent": usage.percent,
                }
            )

        return SkillResult(
            success=True,
            message=(
                f"{len(disks)} disque(s) détecté(s)."
            ),
            data={
                "disks": disks,
            },
        )