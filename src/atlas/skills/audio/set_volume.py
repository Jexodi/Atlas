from pycaw.pycaw import AudioUtilities

from atlas.security.risk import RiskLevel
from atlas.skills.base import (
    Skill,
    SkillResult,
    SkillValidationError,
)


class SetVolumeSkill(Skill):

    name = "audio.set_volume"

    description = "Modifie le volume principal Windows."

    parameters = {
        "type": "object",
        "properties": {
            "volume": {
                "type": "number",
                "minimum": 0,
                "maximum": 100,
                "description": (
                    "Volume principal Windows "
                    "en pourcentage."
                ),
            },
        },
        "required": [
            "volume",
        ],
        "additionalProperties": False,
    }

    risk_level = RiskLevel.SAFE

    required_permission = None

    requires_service = False

    def validate(
        self,
        **kwargs,
    ) -> None:

        volume = kwargs.get(
            "volume"
        )

        if volume is None:
            raise SkillValidationError(
                "Le paramètre 'volume' est obligatoire."
            )

        if not isinstance(
            volume,
            (int, float),
        ):
            raise SkillValidationError(
                "Le volume doit être un nombre."
            )

        if volume < 0 or volume > 100:
            raise SkillValidationError(
                "Le volume doit être compris entre 0 et 100."
            )

    def execute(
        self,
        **kwargs,
    ) -> SkillResult:

        volume_percent = float(
            kwargs["volume"]
        )

        device = AudioUtilities.GetSpeakers()

        endpoint = device.EndpointVolume

        endpoint.SetMasterVolumeLevelScalar(
            volume_percent / 100,
            None,
        )

        return SkillResult(
            success=True,
            message=(
                f"Volume réglé à {round(volume_percent)} %."
            ),
            data={
                "volume_percent": volume_percent,
            },
        )