from enum import Enum


class PermissionMode(str, Enum):
    RESTRICTED = "restricted"
    NORMAL = "normal"
    ADVANCED = "advanced"
    ADMINISTRATOR = "administrator"
    JARVIS = "jarvis"


from dataclasses import dataclass


@dataclass(slots=True)
class PermissionDecision:
    allowed: bool
    confirmation_required: bool
    reason: str