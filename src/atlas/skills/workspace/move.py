from typing import Any

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


class MoveWorkspaceItemSkill(Skill):

    name = "workspace.move"

    description = (
        "Déplace un fichier ou un dossier uniquement "
        "à l'intérieur de la zone sécurisée d'Sideron."
    )

    risk_level = RiskLevel.LOCAL_MODIFICATION

    required_permission = None
    requires_service = False

    parameters = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": (
                    "Chemin relatif de l'élément à déplacer "
                    "dans la zone Sideron."
                ),
            },
            "destination_directory": {
                "type": "string",
                "description": (
                    "Chemin relatif du dossier de destination "
                    "dans la zone Sideron."
                ),
            },
        },
        "required": [
            "source",
            "destination_directory",
        ],
        "additionalProperties": False,
    }

    def __init__(
        self,
        storage: SideronStorage,
    ) -> None:

        self.storage = storage

    def validate(
        self,
        **kwargs: Any,
    ) -> None:

        source = kwargs.get(
            "source"
        )

        destination = kwargs.get(
            "destination_directory"
        )

        if not isinstance(
            source,
            str,
        ) or not source.strip():

            raise SkillValidationError(
                "Le chemin source doit être une chaîne non vide."
            )

        if not isinstance(
            destination,
            str,
        ) or not destination.strip():

            raise SkillValidationError(
                "Le dossier de destination doit être "
                "une chaîne non vide."
            )

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        try:

            destination = self.storage.move(
                source_relative_path=kwargs["source"],
                destination_directory=kwargs[
                    "destination_directory"
                ],
            )

        except SideronStorageError as exc:

            return SkillResult(
                success=False,
                message=str(exc),
            )

        return SkillResult(
            success=True,
            message=(
                f"L'élément a été déplacé vers "
                f"'{destination}'."
            ),
            data={
                "path": str(
                    destination
                ),
            },
        )