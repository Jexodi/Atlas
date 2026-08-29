import json
import re
import time
import uuid

from dataclasses import dataclass
from typing import Any

from atlas.skills.manager import (
    SkillExecutionResult,
    SkillManager,
)

from atlas.skills.registry import (
    SkillRegistry,
)


CONFIRMATION_TIMEOUT_SECONDS = 30.0


@dataclass(slots=True)
class PendingConfirmation:

    confirmation_id: str

    skill_name: str

    arguments: dict[str, Any]

    message: str

    created_at: float

    expires_at: float


class RealtimeToolRouter:

    def __init__(
        self,
        registry: SkillRegistry,
        skill_manager: SkillManager,
        logger,
    ) -> None:

        self.registry = registry
        self.skill_manager = skill_manager
        self.logger = logger

        self.pending_confirmation: (
            PendingConfirmation | None
        ) = None

        # Nom exposé à OpenAI
        # -> nom réel Sideron
        self._tool_to_skill: dict[
            str,
            str,
        ] = {}

        # Nom Sideron
        # -> nom exposé OpenAI
        self._skill_to_tool: dict[
            str,
            str,
        ] = {}

    # =====================================================
    # Tool names
    # =====================================================

    def _make_tool_name(
        self,
        skill_name: str,
    ) -> str:

        return re.sub(
            r"[^a-zA-Z0-9_-]",
            "_",
            skill_name,
        )

    # =====================================================
    # Tools OpenAI
    # =====================================================

    def build_tools(
        self,
    ) -> list[dict[str, Any]]:

        tools: list[
            dict[str, Any]
        ] = []

        self._tool_to_skill.clear()
        self._skill_to_tool.clear()

        # =================================================
        # Skills Sideron
        # =================================================

        for skill in self.registry.list_skills():

            tool_name = (
                self._make_tool_name(
                    skill.name
                )
            )

            existing_skill = (
                self._tool_to_skill.get(
                    tool_name
                )
            )

            if (
                existing_skill is not None
                and existing_skill != skill.name
            ):

                raise ValueError(
                    "Collision de nom Tool : "
                    f"'{existing_skill}' et "
                    f"'{skill.name}' deviennent "
                    f"'{tool_name}'."
                )

            self._tool_to_skill[
                tool_name
            ] = skill.name

            self._skill_to_tool[
                skill.name
            ] = tool_name

            tools.append(
                {
                    "type": "function",
                    "name": tool_name,
                    "description": (
                        skill.description
                    ),
                    "parameters": (
                        skill.parameters
                    ),
                }
            )

            self.logger.debug(
                "Skill exposé à Realtime : "
                "%s -> %s",
                skill.name,
                tool_name,
            )

        # =================================================
        # Confirmation
        # =================================================

        tools.append(
            {
                "type": "function",
                "name": "atlas_confirm_action",
                "description": (
                    "Confirme une action Sideron en attente. "
                    "Utiliser uniquement si l'utilisateur "
                    "vient de confirmer explicitement cette "
                    "action. Utiliser exactement le "
                    "confirmation_id fourni par Sideron."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "confirmation_id": {
                            "type": "string",
                            "description": (
                                "Identifiant exact de "
                                "l'action en attente."
                            ),
                        },
                    },
                    "required": [
                        "confirmation_id",
                    ],
                    "additionalProperties": False,
                },
            }
        )

        tools.append(
            {
                "type": "function",
                "name": "atlas_cancel_action",
                "description": (
                    "Annule l'action Sideron actuellement "
                    "en attente lorsque l'utilisateur refuse "
                    "explicitement son exécution."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "confirmation_id": {
                            "type": "string",
                            "description": (
                                "Identifiant exact de "
                                "l'action à annuler."
                            ),
                        },
                    },
                    "required": [
                        "confirmation_id",
                    ],
                    "additionalProperties": False,
                },
            }
        )

        return tools

    # =====================================================
    # Exécution
    # =====================================================

    def execute(
        self,
        tool_name: str,
        arguments: str | dict,
    ) -> dict[str, Any]:

        parsed_arguments = (
            self._parse_arguments(
                arguments
            )
        )

        if parsed_arguments is None:

            return {
                "success": False,
                "skill": tool_name,
                "message": (
                    "Arguments JSON invalides."
                ),
                "data": None,
                "confirmation_required": False,
                "denied": False,
            }

        # =================================================
        # Confirmation
        # =================================================

        if tool_name == "atlas_confirm_action":

            return (
                self._confirm_pending_action(
                    parsed_arguments.get(
                        "confirmation_id"
                    )
                )
            )

        # =================================================
        # Annulation
        # =================================================

        if tool_name == "atlas_cancel_action":

            return (
                self._cancel_pending_action(
                    parsed_arguments.get(
                        "confirmation_id"
                    )
                )
            )

        # =================================================
        # Résolution Tool -> Skill
        # =================================================

        skill_name = (
            self._tool_to_skill.get(
                tool_name
            )
        )

        if skill_name is None:

            self.logger.warning(
                "Tool Realtime inconnu : %s",
                tool_name,
            )

            return {
                "success": False,
                "skill": tool_name,
                "message": (
                    "Outil Realtime inconnu : "
                    f"{tool_name}"
                ),
                "data": None,
                "confirmation_required": False,
                "denied": True,
            }

        self.logger.info(
            "Tool call Realtime : "
            "%s -> %s %s",
            tool_name,
            skill_name,
            parsed_arguments,
        )

        # =================================================
        # Exécution initiale
        # =================================================

        result: SkillExecutionResult = (
            self.skill_manager.execute(
                skill_name,
                **parsed_arguments,
            )
        )

        # =================================================
        # Confirmation requise
        # =================================================

        if result.confirmation_required:

            confirmation = (
                self._create_pending_confirmation(
                    skill_name=skill_name,
                    arguments=parsed_arguments,
                    message=result.message,
                )
            )

            return {
                "success": False,
                "skill": result.skill_name,
                "message": result.message,
                "data": {
                    "confirmation_id": (
                        confirmation.confirmation_id
                    ),
                    "expires_in_seconds": int(
                        CONFIRMATION_TIMEOUT_SECONDS
                    ),
                    "action": (
                        confirmation.skill_name
                    ),
                    "parameters": (
                        confirmation.arguments
                    ),
                },
                "confirmation_required": True,
                "denied": False,
            }

        return {
            "success": result.success,
            "skill": result.skill_name,
            "message": result.message,
            "data": result.data,
            "confirmation_required": False,
            "denied": result.denied,
        }

    # =====================================================
    # Parsing
    # =====================================================

    def _parse_arguments(
        self,
        arguments: str | dict,
    ) -> dict[str, Any] | None:

        if isinstance(
            arguments,
            dict,
        ):

            return arguments

        if not isinstance(
            arguments,
            str,
        ):

            return None

        try:

            parsed = json.loads(
                arguments
            )

        except json.JSONDecodeError:

            return None

        if not isinstance(
            parsed,
            dict,
        ):

            return None

        return parsed

    # =====================================================
    # Création confirmation
    # =====================================================

    def _create_pending_confirmation(
        self,
        skill_name: str,
        arguments: dict[str, Any],
        message: str,
    ) -> PendingConfirmation:

        now = time.monotonic()

        # Une seule confirmation peut être active.
        if self.pending_confirmation is not None:

            previous = (
                self.pending_confirmation
            )

            self.logger.info(
                "Confirmation précédente remplacée : "
                "%s (%s)",
                previous.skill_name,
                previous.confirmation_id,
            )

        confirmation = PendingConfirmation(
            confirmation_id=uuid.uuid4().hex,
            skill_name=skill_name,
            arguments=dict(
                arguments
            ),
            message=message,
            created_at=now,
            expires_at=(
                now
                + CONFIRMATION_TIMEOUT_SECONDS
            ),
        )

        self.pending_confirmation = (
            confirmation
        )

        self.logger.info(
            "Action mise en attente : "
            "%s | confirmation=%s | expiration=%.0fs",
            skill_name,
            confirmation.confirmation_id,
            CONFIRMATION_TIMEOUT_SECONDS,
        )

        return confirmation

    # =====================================================
    # Expiration
    # =====================================================

    def _get_valid_pending_confirmation(
        self,
    ) -> PendingConfirmation | None:

        pending = (
            self.pending_confirmation
        )

        if pending is None:

            return None

        now = time.monotonic()

        if now >= pending.expires_at:

            self.logger.info(
                "Confirmation expirée : "
                "%s (%s)",
                pending.skill_name,
                pending.confirmation_id,
            )

            self.pending_confirmation = None

            return None

        return pending

    # =====================================================
    # Confirmation
    # =====================================================

    def _confirm_pending_action(
        self,
        confirmation_id: Any,
    ) -> dict[str, Any]:

        pending = (
            self._get_valid_pending_confirmation()
        )

        if pending is None:

            return {
                "success": False,
                "skill": None,
                "message": (
                    "La confirmation a expiré ou "
                    "aucune action n'est en attente."
                ),
                "data": None,
                "confirmation_required": False,
                "denied": False,
            }

        if not isinstance(
            confirmation_id,
            str,
        ):

            return {
                "success": False,
                "skill": pending.skill_name,
                "message": (
                    "Identifiant de confirmation manquant."
                ),
                "data": None,
                "confirmation_required": True,
                "denied": False,
            }

        if (
            confirmation_id
            != pending.confirmation_id
        ):

            self.logger.warning(
                "Confirmation refusée : "
                "identifiant incorrect."
            )

            return {
                "success": False,
                "skill": pending.skill_name,
                "message": (
                    "Cette confirmation ne correspond "
                    "pas à l'action actuellement en attente."
                ),
                "data": {
                    "confirmation_id": (
                        pending.confirmation_id
                    ),
                },
                "confirmation_required": True,
                "denied": False,
            }

        self.logger.info(
            "Confirmation reçue pour : "
            "%s (%s)",
            pending.skill_name,
            pending.confirmation_id,
        )

        # Suppression AVANT exécution :
        # impossible de confirmer deux fois.
        self.pending_confirmation = None

        result: SkillExecutionResult = (
            self.skill_manager.execute(
                pending.skill_name,
                confirmed=True,
                **pending.arguments,
            )
        )

        return {
            "success": result.success,
            "skill": result.skill_name,
            "message": result.message,
            "data": result.data,
            "confirmation_required": (
                result.confirmation_required
            ),
            "denied": result.denied,
        }

    # =====================================================
    # Annulation
    # =====================================================

    def _cancel_pending_action(
        self,
        confirmation_id: Any,
    ) -> dict[str, Any]:

        pending = (
            self._get_valid_pending_confirmation()
        )

        if pending is None:

            return {
                "success": False,
                "skill": None,
                "message": (
                    "La confirmation a expiré ou "
                    "aucune action n'est en attente."
                ),
                "data": None,
                "confirmation_required": False,
                "denied": False,
            }

        if not isinstance(
            confirmation_id,
            str,
        ):

            return {
                "success": False,
                "skill": pending.skill_name,
                "message": (
                    "Identifiant de confirmation manquant."
                ),
                "data": None,
                "confirmation_required": True,
                "denied": False,
            }

        if (
            confirmation_id
            != pending.confirmation_id
        ):

            return {
                "success": False,
                "skill": pending.skill_name,
                "message": (
                    "Cette annulation ne correspond "
                    "pas à l'action actuellement en attente."
                ),
                "data": {
                    "confirmation_id": (
                        pending.confirmation_id
                    ),
                },
                "confirmation_required": True,
                "denied": False,
            }

        self.logger.info(
            "Action annulée par l'utilisateur : "
            "%s (%s)",
            pending.skill_name,
            pending.confirmation_id,
        )

        self.pending_confirmation = None

        return {
            "success": True,
            "skill": pending.skill_name,
            "message": (
                "Action annulée à la demande "
                "de l'utilisateur."
            ),
            "data": None,
            "confirmation_required": False,
            "denied": False,
        }