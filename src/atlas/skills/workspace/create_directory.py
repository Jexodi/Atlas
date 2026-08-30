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


class CreateWorkspaceDirectorySkill(Skill):

    name = "workspace.directory_create"

    description = (
        "Crée un dossier uniquement dans la zone de stockage "
        "sécurisée d'Sideron. "
        "Le chemin doit être relatif à la zone Sideron."
    )

    risk_level = RiskLevel.SAFE

    required_permission = None

    requires_service = False

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Chemin relatif du dossier à créer dans "
                    "la zone Sideron. "
                    "Exemple : Projects/MonProjet"
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
    ) -> None:

        self.storage = storage

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
                "Le chemin doit être une chaîne."
            )

        if not path.strip():

            raise SkillValidationError(
                "Le chemin ne peut pas être vide."
            )

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        path = kwargs["path"]

        try:

            destination = (
                self.storage.create_directory(
                    path
                )
            )

        except SideronStorageError as exc:

            return SkillResult(
                success=False,
                message=str(exc),
            )

        return SkillResult(
            success=True,
            message=(
                f"Le dossier '{destination.name}' "
                "a été créé dans la zone Sideron."
            ),
            data={
                "path": str(
                    destination
                ),
            },
        )