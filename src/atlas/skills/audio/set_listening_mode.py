from typing import Any

from atlas.audio.mode import ListeningMode
from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class SetListeningModeSkill(Skill):

    name = "audio.set_listening_mode"

    description = (
        "Change le mode d'écoute vocale d'Sideron. "
        "Utilise wake_word pour le mode vocal, Discord ou lorsque "
        "l'utilisateur veut qu'Sideron attende le mot de réveil. "
        "Utilise continuous pour le mode normal ou l'écoute continue."
    )

    parameters = {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "continuous",
                    "wake_word",
                ],
            },
        },
        "required": [
            "mode",
        ],
        "additionalProperties": False,
    }

    risk_level = RiskLevel.SAFE
    required_permission = None
    requires_service = False

    def __init__(
        self,
        audio_manager,
        config,
    ) -> None:

        self.audio_manager = audio_manager
        self.config = config

    def execute(
        self,
        mode: str,
        **kwargs: Any,
    ) -> SkillResult:

        try:
            active_mode = (
                self.audio_manager
                .set_listening_mode(
                    ListeningMode.from_value(
                        mode
                    )
                )
            )
        except (
            TypeError,
            ValueError,
            RuntimeError,
        ) as exc:
            return SkillResult(
                success=False,
                message=str(
                    exc
                ),
            )

        self.config.set(
            "audio.listening_mode",
            active_mode.value,
        )

        self.config.set(
            "audio.continuous_listening",
            active_mode
            == ListeningMode.CONTINUOUS,
        )

        self.config.save()

        if active_mode == ListeningMode.WAKE_WORD:
            message = (
                "Mode vocal activé. "
                "Sideron attend désormais le mot de réveil."
            )
        else:
            message = (
                "Écoute continue activée."
            )

        return SkillResult(
            success=True,
            message=message,
            data={
                "mode": active_mode.value,
            },
        )
