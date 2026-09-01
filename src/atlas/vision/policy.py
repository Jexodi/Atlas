from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisionCaptureDecision:
    allowed: bool
    reason: str


class VisionPolicy:
    """Politique de préparation Vision : aucune capture implicite par défaut."""

    def evaluate_capture(
        self,
        *,
        user_requested: bool = False,
        explicit_permission: bool = False,
        privacy_mode: bool = False,
    ) -> VisionCaptureDecision:
        if privacy_mode:
            return VisionCaptureDecision(False, "Le mode Confidentialité bloque la capture d'écran.")

        if user_requested:
            return VisionCaptureDecision(True, "Capture demandée explicitement par l'utilisateur.")

        if explicit_permission:
            return VisionCaptureDecision(True, "Capture autorisée explicitement par la configuration utilisateur.")

        return VisionCaptureDecision(
            False,
            "Aucune capture automatique : une demande utilisateur ou une permission explicite est requise.",
        )
