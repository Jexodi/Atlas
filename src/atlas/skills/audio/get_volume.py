from pycaw.pycaw import AudioUtilities

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class GetVolumeSkill(Skill):

    name = "audio.get_volume"

    description = "Retourne le volume principal Windows."

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    def execute(
        self,
        **kwargs,
    ) -> SkillResult:

        device = AudioUtilities.GetSpeakers()

        volume = device.EndpointVolume

        current_volume = volume.GetMasterVolumeLevelScalar()

        percent = round(
            current_volume * 100
        )

        muted = bool(
            volume.GetMute()
        )

        return SkillResult(
            success=True,
            message=f"Volume actuel : {percent} %",
            data={
                "volume_percent": percent,
                "muted": muted,
            },
        )