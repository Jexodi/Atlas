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


class ListDirectorySkill(Skill):

    name = "directory.list"

    description = (
        "Liste les fichiers et sous-dossiers contenus dans un dossier Windows. "
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
                    "Chemin Windows absolu du dossier à parcourir."
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

        path = kwargs["path"]

        try:

            entries = self.storage.list_directory(
                path
            )

        except AtlasStorageError as exc:

            return SkillResult(
                success=False,
                message=str(exc),
            )

        serialized_entries = []

        for entry in entries:

            serialized_entries.append(
                {
                    "name": entry.name,
                    "path": str(
                        entry.path
                    ),
                    "type": entry.entry_type,
                    "size": entry.size,
                }
            )

        return SkillResult(
            success=True,
            message=(
                f"{len(serialized_entries)} élément(s) "
                "trouvé(s) dans le dossier."
            ),
            data={
                "path": path,
                "entries": serialized_entries,
                "count": len(
                    serialized_entries
                ),
            },
        )