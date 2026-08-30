from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from atlas.security.risk import RiskLevel


@dataclass(slots=True)
class SkillResult:
    success: bool
    message: str
    data: Any = None


class SkillValidationError(ValueError):
    pass


class Skill(ABC):

    name: str
    description: str

    risk_level: RiskLevel = RiskLevel.SAFE

    required_permission: str | None = None

    requires_service: bool = False

    # Si True, ce Skill nécessite toujours une confirmation
    # explicite, quel que soit le mode de permission.
    always_requires_confirmation: bool = False

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }

    @abstractmethod
    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:
        raise NotImplementedError

    def validate(
        self,
        **kwargs: Any,
    ) -> None:
        pass

    def get_confirmation_message(
        self,
        **kwargs: Any,
    ) -> str:
        """
        Texte présenté à l'utilisateur lorsqu'une
        confirmation est nécessaire.

        Les Skills sensibles peuvent redéfinir cette
        méthode afin de fournir un message précis.
        """

        return (
            "Cette action nécessite une confirmation explicite."
        )