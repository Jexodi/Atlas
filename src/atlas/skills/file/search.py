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


class SearchFileSkill(Skill):

    name = "file.search"

    description = (
        "Recherche des fichiers ou dossiers par leur nom "
        "dans un emplacement du PC. "
        "La recherche est strictement en lecture seule."
    )

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    parameters = {
        "type": "object",
        "properties": {
            "root": {
                "type": "string",
                "description": (
                    "Dossier Windows à partir duquel effectuer la recherche."
                ),
            },
            "query": {
                "type": "string",
                "description": (
                    "Nom ou partie du nom du fichier ou dossier recherché."
                ),
            },
        },
        "required": [
            "root",
            "query",
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

        root = kwargs.get(
            "root"
        )

        query = kwargs.get(
            "query"
        )

        if not isinstance(
            root,
            str,
        ):
            raise SkillValidationError(
                "La racine de recherche doit être une chaîne."
            )

        if not root.strip():
            raise SkillValidationError(
                "La racine de recherche ne peut pas être vide."
            )

        if not isinstance(
            query,
            str,
        ):
            raise SkillValidationError(
                "La recherche doit être une chaîne."
            )

        if not query.strip():
            raise SkillValidationError(
                "La recherche ne peut pas être vide."
            )

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        root = kwargs["root"]
        query = kwargs["query"]

        try:

            results = self.storage.search(
                root=root,
                query=query,
                max_results=50,
            )

        except AtlasStorageError as exc:

            return SkillResult(
                success=False,
                message=str(exc),
            )

        serialized_results = []

        for result in results:

            serialized_results.append(
                {
                    "name": result.name,
                    "path": str(
                        result.path
                    ),
                    "type": result.entry_type,
                    "size": result.size,
                }
            )

        if not serialized_results:

            return SkillResult(
                success=True,
                message=(
                    f"Aucun fichier ou dossier correspondant à "
                    f"'{query}' n'a été trouvé."
                ),
                data={
                    "query": query,
                    "root": root,
                    "results": [],
                    "count": 0,
                },
            )

        return SkillResult(
            success=True,
            message=(
                f"{len(serialized_results)} résultat(s) trouvé(s) "
                f"pour '{query}'."
            ),
            data={
                "query": query,
                "root": root,
                "results": serialized_results,
                "count": len(
                    serialized_results
                ),
            },
        )