from typing import Any

from atlas.security.risk import RiskLevel

from atlas.skills.base import (
    Skill,
    SkillResult,
    SkillValidationError,
)

from atlas.storage import (
    AtlasStorage,
    AtlasStorageError,
)


class RenameWorkspaceItemSkill(Skill):

    name = "workspace.rename"

    description = (
        "Renomme un fichier ou un dossier uniquement "
        "à l'intérieur de la zone sécurisée d'Atlas."
    )

    risk_level = RiskLevel.LOCAL_MODIFICATION

    required_permission = None
    requires_service = False

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Chemin relatif de l'élément dans la zone Atlas."
                ),
            },
            "new_name": {
                "type": "string",
                "description": (
                    "Nouveau nom du fichier ou dossier, "
                    "sans chemin."
                ),
            },
        },
        "required": [
            "path",
            "new_name",
        ],
        "additionalProperties": False,
    }

    def __init__(
        self,
        storage: AtlasStorage,
    ) -> None:

        self.storage = storage

    def validate(
        self,
        **kwargs: Any,
    ) -> None:

        path = kwargs.get(
            "path"
        )

        new_name = kwargs.get(
            "new_name"
        )

        if not isinstance(
            path,
            str,
        ) or not path.strip():

            raise SkillValidationError(
                "Le chemin doit être une chaîne non vide."
            )

        if not isinstance(
            new_name,
            str,
        ) or not new_name.strip():

            raise SkillValidationError(
                "Le nouveau nom doit être une chaîne non vide."
            )

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        try:

            destination = self.storage.rename(
                relative_path=kwargs["path"],
                new_name=kwargs["new_name"],
            )

        except AtlasStorageError as exc:

            return SkillResult(
                success=False,
                message=str(exc),
            )

        return SkillResult(
            success=True,
            message=(
                f"L'élément a été renommé en "
                f"'{destination.name}'."
            ),
            data={
                "path": str(
                    destination
                ),
            },
        )