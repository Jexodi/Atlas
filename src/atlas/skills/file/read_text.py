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


class ReadTextFileSkill(Skill):

    name = "file.read_text"

    description = (
        "Lit le contenu d'un fichier texte présent sur le PC. "
        "Cette opération est strictement en lecture seule."
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
                    "Chemin Windows absolu du fichier texte à lire."
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
                "Le chemin du fichier doit être une chaîne de caractères."
            )

        if not path.strip():
            raise SkillValidationError(
                "Le chemin du fichier ne peut pas être vide."
            )

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        path = kwargs["path"]

        try:

            content = self.storage.read_text(
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
                "Le fichier texte a été lu avec succès."
            ),
            data={
                "path": path,
                "content": content,
            },
        )