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


class DeleteWorkspaceItemSkill(Skill):

    name = "workspace.delete"

    description = (
        "Supprime définitivement un fichier ou un dossier "
        "uniquement dans la zone sécurisée d'Atlas. "
        "Cette action nécessite toujours une confirmation "
        "explicite de l'utilisateur."
    )

    risk_level = RiskLevel.LOCAL_MODIFICATION

    required_permission = None

    requires_service = False

    always_requires_confirmation = True

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Chemin relatif du fichier ou dossier "
                    "à supprimer dans la zone Atlas. "
                    "Exemple : Projects/Test/temp.txt"
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

        # La validation du confinement reste assurée
        # par AtlasStorage.
        self.storage.workspace_path(
            path
        )

    def get_confirmation_message(
        self,
        **kwargs: Any,
    ) -> str:

        path = kwargs["path"]

        target = (
            self.storage.workspace_path(
                path
            )
        )

        if target.exists():

            if target.is_dir():

                item_type = "le dossier"

            else:

                item_type = "le fichier"

        else:

            item_type = "l'élément"

        return (
            f"Confirmez-vous la suppression définitive de "
            f"{item_type} '{path}' dans la zone Atlas ?"
        )

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        path = kwargs["path"]

        try:

            target = (
                self.storage.workspace_path(
                    path
                )
            )

            if target.is_dir():

                item_type = "dossier"

            else:

                item_type = "fichier"

            item_name = target.name

            self.storage.delete(
                path
            )

        except AtlasStorageError as exc:

            return SkillResult(
                success=False,
                message=str(exc),
            )

        return SkillResult(
            success=True,
            message=(
                f"Le {item_type} '{item_name}' "
                "a été supprimé de la zone Atlas."
            ),
            data={
                "path": path,
                "deleted": True,
                "type": item_type,
            },
        )