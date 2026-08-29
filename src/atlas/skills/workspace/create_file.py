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


class CreateWorkspaceFileSkill(Skill):

    name = "workspace.file_create"

    description = (
        "Crée un nouveau fichier texte uniquement dans "
        "la zone sécurisée d'Sideron. "
        "Cette opération ne peut pas écrire ailleurs sur le PC."
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
                    "Chemin relatif du fichier dans la zone Sideron. "
                    "Exemple : Documents/notes.txt"
                ),
            },
            "content": {
                "type": "string",
                "description": (
                    "Contenu texte initial du fichier."
                ),
            },
        },
        "required": [
            "path",
            "content",
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

        content = kwargs.get(
            "content"
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

        if not isinstance(
            content,
            str,
        ):

            raise SkillValidationError(
                "Le contenu doit être une chaîne."
            )

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        path = kwargs["path"]
        content = kwargs["content"]

        try:

            destination = (
                self.storage.write_text(
                    relative_path=path,
                    content=content,
                    overwrite=False,
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
                f"Le fichier '{destination.name}' "
                "a été créé dans la zone Sideron."
            ),
            data={
                "path": str(
                    destination
                ),
            },
        )