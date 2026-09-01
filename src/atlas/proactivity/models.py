from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProactiveSuggestion:
    title: str
    message: str
    source_event: str
    severity: str = "info"
    kind: str = "suggestion"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)
