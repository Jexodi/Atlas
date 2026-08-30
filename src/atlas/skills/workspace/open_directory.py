from __future__ import annotations

from typing import Any

from atlas.core.event_bus import EventBus
from atlas.security.risk import RiskLevel
from atlas.skills.base import (
    Skill,
    SkillResult,
    SkillValidationError,
)
from atlas.storage import (
    SideronStorage,
    SideronStorageError,
)


class OpenWorkspaceDirectorySkill(Skill):

    name = "workspace.open_directory"

    description = (
        "Affiche un dossier existant de la zone Sideron dans "
        "l'interface Workspace d'Sideron. "
        "Le chemin doit être relatif à la zone Sideron. "
        "Exemples : Documents, Projects, Imports ou Projects/SIDERON."
    )

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Chemin relatif du dossier à afficher dans "
                    "l'interface Sideron. Exemple : Projects/SIDERON"
                ),
            },
        },
        "required": [
            "path",
        ],
        "additionalProperties": False,
    }

    def __init__(
        self,
        storage: SideronStorage,
        event_bus: EventBus,
    ) -> None:

        self.storage = storage
        self.event_bus = event_bus

    def validate(
        self,
        **kwargs: Any,
    ) -> None:

        path = kwargs.get(
            "path"
        )

        if not isinstance(
            path,
            str,
        ):

            raise SkillValidationError(
                "Le chemin du dossier doit être une chaîne."
            )

        if not path.strip():

            raise SkillValidationError(
                "Le chemin du dossier ne peut pas être vide."
            )

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        relative_path = (
            kwargs["path"].strip()
        )

        try:

            directory = (
                self.storage.workspace_path(
                    relative_path
                )
            )

            if not directory.exists():

                return SkillResult(
                    success=False,
                    message=(
                        f"Le dossier '{relative_path}' "
                        "n'existe pas dans la zone Sideron."
                    ),
                )

            if not directory.is_dir():

                return SkillResult(
                    success=False,
                    message=(
                        f"'{relative_path}' n'est pas un dossier."
                    ),
                )

        except SideronStorageError as exc:

            return SkillResult(
                success=False,
                message=str(exc),
            )

        self.event_bus.publish(
            "ui.workspace.open_directory",
            {
                "path": str(
                    directory
                ),
            },
        )

        return SkillResult(
            success=True,
            message=(
                f"Le dossier '{directory.name}' "
                "est affiché dans l'interface Sideron."
            ),
            data={
                "path": str(
                    directory
                ),
            },
        )
