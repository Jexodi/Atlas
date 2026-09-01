from __future__ import annotations

from typing import Any

from atlas.memory import MemoryManager
from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


class SearchMemorySkill(Skill):
    name = "memory.search"
    description = (
        "Recherche localement dans la mémoire persistante de SIDERON. "
        "À utiliser de manière proactive avant de répondre ou d'agir lorsqu'une demande "
        "dépend d'une préférence, d'un alias ou d'une information personnelle déjà apprise "
        "(par exemple : 'mon casque', 'comme d'habitude', 'ma préférence audio'). "
        "Utiliser une requête courte avec les mots-clés importants plutôt que recopier toute la phrase."
    )
    risk_level = RiskLevel.READ_ONLY
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Texte ou mots-clés à rechercher."},
            "category": {
                "type": "string",
                "enum": sorted(MemoryManager.CATEGORIES),
                "description": "Catégorie facultative à filtrer.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "description": "Nombre maximal de résultats.",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def __init__(self, memory: MemoryManager) -> None:
        self.memory = memory

    def validate(self, **kwargs: Any) -> None:
        self.memory._clean_required_text(kwargs.get("query"), "La recherche", 500)
        if kwargs.get("category") is not None:
            self.memory.validate_category(kwargs["category"])
        self.memory.validate_limit(kwargs.get("limit", 10), maximum=50)

    def execute(self, **kwargs: Any) -> SkillResult:
        records = self.memory.search(
            kwargs["query"],
            category=kwargs.get("category"),
            limit=kwargs.get("limit", 10),
        )
        return SkillResult(
            success=True,
            message=f"{len(records)} souvenir(s) correspondant(s) trouvé(s).",
            data={"memories": [record.to_dict() for record in records]},
        )
