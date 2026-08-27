from pycaw.pycaw import AudioUtilities

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class MuteSkill(Skill):

    name = "audio.mute"

    description = "Coupe le son principal Windows."

    risk_level = RiskLevel.SAFE

    required_permission = None

    requires_service = False

    def execute(
        self,
        **kwargs,
    ) -> SkillResult:

        device = AudioUtilities.GetSpeakers()

        endpoint = device.EndpointVolume

        endpoint.SetMute(
            1,
            None,
        )

        return SkillResult(
            success=True,
            message="Son coupé.",
        )


class UnmuteSkill(Skill):

    name = "audio.unmute"

    description = "Réactive le son principal Windows."

    risk_level = RiskLevel.SAFE

    required_permission = None

    requires_service = False

    def execute(
        self,
        **kwargs,
    ) -> SkillResult:

        device = AudioUtilities.GetSpeakers()

        endpoint = device.EndpointVolume

        endpoint.SetMute(
            0,
            None,
        )

        return SkillResult(
            success=True,
            message="Son réactivé.",
        )