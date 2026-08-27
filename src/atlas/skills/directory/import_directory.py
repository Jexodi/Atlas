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


class ImportDirectorySkill(Skill):

    name = "directory.import"

    description = (
        "Copie un dossier existant depuis le PC vers "
        "la zone de stockage sécurisée d'Atlas. "
        "Le dossier source n'est jamais modifié."
    )

    risk_level = RiskLevel.SAFE

    required_permission = None

    requires_service = False

    parameters = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": (
                    "Chemin Windows absolu du dossier "
                    "à copier dans la zone Atlas."
                ),
            },
            "destination_directory": {
                "type": "string",
                "description": (
                    "Dossier relatif dans la zone Atlas. "
                    "Par défaut : Imports."
                ),
                "default": "Imports",
            },
        },
        "required": [
            "source",
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

        source = kwargs.get(
            "source"
        )

        destination = kwargs.get(
            "destination_directory",
            "Imports",
        )

        if not isinstance(
            source,
            str,
        ):
            raise SkillValidationError(
                "Le chemin source doit être une chaîne."
            )

        if not source.strip():
            raise SkillValidationError(
                "Le chemin source ne peut pas être vide."
            )

        if not isinstance(
            destination,
            str,
        ):
            raise SkillValidationError(
                "Le dossier de destination doit être une chaîne."
            )

        if not destination.strip():
            raise SkillValidationError(
                "Le dossier de destination ne peut pas être vide."
            )

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        source = kwargs["source"]

        destination_directory = kwargs.get(
            "destination_directory",
            "Imports",
        )

        try:

            result = self.storage.import_directory(
                source=source,
                destination_directory=destination_directory,
            )

        except AtlasStorageError as exc:

            return SkillResult(
                success=False,
                message=str(exc),
            )

        return SkillResult(
            success=True,
            message=(
                f"Le dossier '{result.source.name}' "
                "a été copié dans la zone Atlas."
            ),
            data={
                "source": str(
                    result.source
                ),
                "destination": str(
                    result.destination
                ),
                "copied": result.copied,
            },
        )