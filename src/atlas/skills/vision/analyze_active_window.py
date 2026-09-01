from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult
from atlas.storage import SideronStorage
from atlas.vision import VisionPolicy
from atlas.vision.capture import ActiveWindowCapturer


class AnalyzeActiveWindowSkill(Skill):
    name = "vision.analyze_active_window"
    description = (
        "Capture et analyse visuellement la fenêtre Windows actuellement active. "
        "À utiliser uniquement lorsque l'utilisateur demande explicitement de regarder, "
        "analyser ou expliquer ce qui est affiché à l'écran ou dans la fenêtre active. "
        "La capture n'est jamais automatique."
    )
    risk_level = RiskLevel.READ_ONLY
    always_requires_confirmation = True
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "Question précise à poser à OpenAI au sujet de la fenêtre active. "
                    "Ne pas inclure de secrets ni inventer de contenu non visible."
                ),
            }
        },
        "required": ["prompt"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        *,
        storage: SideronStorage,
        analyzer,
        policy: VisionPolicy,
        privacy_mode_provider,
        logger,
    ) -> None:
        self.storage = storage
        self.analyzer = analyzer
        self.policy = policy
        self.privacy_mode_provider = privacy_mode_provider
        self.logger = logger
        self.capturer = ActiveWindowCapturer()

    def validate(self, **kwargs: Any) -> None:
        prompt = str(kwargs.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("Une question visuelle est requise.")
        if len(prompt) > 2000:
            raise ValueError("La question visuelle est trop longue.")

    def get_confirmation_message(self, **kwargs: Any) -> str:
        return (
            "SIDERON va capturer la fenêtre actuellement active et envoyer cette image à OpenAI "
            "pour l'analyser. Autorisez-vous cette capture ponctuelle ?"
        )

    def execute(self, **kwargs: Any) -> SkillResult:
        privacy_mode = bool(self.privacy_mode_provider())
        decision = self.policy.evaluate_capture(
            user_requested=True,
            explicit_permission=False,
            privacy_mode=privacy_mode,
        )
        if not decision.allowed:
            return SkillResult(success=False, message=decision.reason)

        temp_dir = self.storage.workspace_path("Temp/Vision")
        capture = self.capturer.capture(temp_dir)
        self.logger.info(
            "Capture Vision ponctuelle : title=%r pid=%s size=%dx%d",
            capture.title,
            capture.process_id,
            capture.width,
            capture.height,
        )

        try:
            prompt = (
                "Analyse uniquement ce qui est visible dans cette capture de la fenêtre active SIDERON. "
                "Réponds en français. Si une information n'est pas lisible ou visible, dis-le clairement. "
                "N'invente aucune donnée.\n\n"
                f"Demande utilisateur : {str(kwargs['prompt']).strip()}"
            )
            analysis = self.analyzer.analyze_image(capture.path, prompt)
        finally:
            try:
                Path(capture.path).unlink(missing_ok=True)
            except OSError:
                self.logger.warning("Impossible de supprimer la capture Vision temporaire : %s", capture.path)

        return SkillResult(
            success=True,
            message="Analyse visuelle de la fenêtre active terminée.",
            data={
                "analysis": analysis,
                "window_title": capture.title,
                "process_id": capture.process_id,
                "width": capture.width,
                "height": capture.height,
                "capture_persisted": False,
            },
        )
