from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class ScheduledTask:
    id: int
    kind: str
    message: str
    run_at: datetime
    status: str
    created_at: datetime
    completed_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "message": self.message,
            "run_at": self.run_at.isoformat(),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
