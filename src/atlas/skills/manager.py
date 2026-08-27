from dataclasses import dataclass
from typing import Any

from atlas.core.event_bus import EventBus
from atlas.security.permissions import PermissionMode
from atlas.security.policy import PermissionEngine
from atlas.skills.base import SkillResult
from atlas.skills.registry import SkillRegistry


@dataclass(slots=True)
class SkillExecutionResult:
    success: bool
    skill_name: str
    message: str
    data: Any = None

    confirmation_required: bool = False
    denied: bool = False


class SkillManager:

    def __init__(
        self,
        registry: SkillRegistry,
        permission_engine: PermissionEngine,
        event_bus: EventBus,
        permission_mode: PermissionMode,
        logger,
    ) -> None:

        self.registry = registry
        self.permission_engine = permission_engine
        self.event_bus = event_bus
        self.permission_mode = permission_mode
        self.logger = logger

    def execute(
        self,
        skill_name: str,
        confirmed: bool = False,
        **kwargs: Any,
    ) -> SkillExecutionResult:

        skill = self.registry.get(
            skill_name
        )

        if skill is None:

            self.logger.warning(
                "Skill inconnu : %s",
                skill_name,
            )

            return SkillExecutionResult(
                success=False,
                skill_name=skill_name,
                message=(
                    f"Skill inconnu : {skill_name}"
                ),
            )

        self.logger.debug(
            "Préparation du Skill '%s'.",
            skill.name,
        )

        # =================================================
        # Validation
        # =================================================

        try:

            skill.validate(
                **kwargs
            )

        except Exception as exc:

            self.logger.warning(
                "Validation refusée pour '%s' : %s",
                skill.name,
                exc,
            )

            return SkillExecutionResult(
                success=False,
                skill_name=skill.name,
                message=(
                    f"Paramètres invalides : {exc}"
                ),
            )

        # =================================================
        # Politique générale
        # =================================================

        decision = (
            self.permission_engine.evaluate(
                risk_level=skill.risk_level,
                permission_mode=self.permission_mode,
            )
        )

        if not decision.allowed:

            self.logger.warning(
                "Skill '%s' refusé : %s",
                skill.name,
                decision.reason,
            )

            self.event_bus.publish(
                "skill.denied",
                {
                    "skill": skill.name,
                    "reason": decision.reason,
                },
            )

            return SkillExecutionResult(
                success=False,
                skill_name=skill.name,
                message=decision.reason,
                denied=True,
            )

        # =================================================
        # Confirmation
        # =================================================

        confirmation_required = (
            decision.confirmation_required
            or skill.always_requires_confirmation
        )

        if (
            confirmation_required
            and not confirmed
        ):

            if skill.always_requires_confirmation:

                reason = (
                    skill.get_confirmation_message(
                        **kwargs
                    )
                )

            else:

                reason = decision.reason

            self.logger.info(
                "Confirmation requise pour '%s' : %s",
                skill.name,
                reason,
            )

            self.event_bus.publish(
                "skill.confirmation_required",
                {
                    "skill": skill.name,
                    "risk_level": (
                        skill.risk_level.name
                    ),
                    "parameters": kwargs,
                    "reason": reason,
                },
            )

            return SkillExecutionResult(
                success=False,
                skill_name=skill.name,
                message=reason,
                confirmation_required=True,
            )

        # =================================================
        # Exécution
        # =================================================

        self.event_bus.publish(
            "skill.started",
            {
                "skill": skill.name,
                "parameters": kwargs,
            },
        )

        self.logger.info(
            "Exécution du Skill '%s'.",
            skill.name,
        )

        try:

            result: SkillResult = (
                skill.execute(
                    **kwargs
                )
            )

        except Exception as exc:

            self.logger.exception(
                "Erreur pendant l'exécution "
                "du Skill '%s'.",
                skill.name,
            )

            self.event_bus.publish(
                "skill.failed",
                {
                    "skill": skill.name,
                    "error": str(exc),
                },
            )

            return SkillExecutionResult(
                success=False,
                skill_name=skill.name,
                message=str(exc),
            )

        # =================================================
        # Résultat
        # =================================================

        if result.success:

            self.event_bus.publish(
                "skill.completed",
                {
                    "skill": skill.name,
                    "message": result.message,
                    "data": result.data,
                },
            )

            self.logger.info(
                "Skill '%s' terminé : %s",
                skill.name,
                result.message,
            )

        else:

            self.event_bus.publish(
                "skill.failed",
                {
                    "skill": skill.name,
                    "error": result.message,
                },
            )

            self.logger.warning(
                "Échec du Skill '%s' : %s",
                skill.name,
                result.message,
            )

        return SkillExecutionResult(
            success=result.success,
            skill_name=skill.name,
            message=result.message,
            data=result.data,
        )