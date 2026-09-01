from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atlas.core.event_bus import EventBus

from .models import ScheduledTask
from .repository import AutomationRepository


class AutomationValidationError(ValueError):
    pass


class AutomationManager:
    MAX_MESSAGE_LENGTH = 1000
    MAX_DELAY_SECONDS = 365 * 24 * 60 * 60
    STATUSES = {"pending", "completed", "cancelled"}

    def __init__(self, database_path: str | Path, event_bus: EventBus, logger) -> None:
        self.database_path = Path(database_path)
        self.events = event_bus
        self.logger = logger
        self.repository = AutomationRepository(self.database_path)

    def initialize(self) -> None:
        self.repository.initialize()

    def create_reminder(
        self,
        *,
        message: str,
        delay_seconds: int | None = None,
        run_at: str | None = None,
    ) -> ScheduledTask:
        clean_message = self.validate_message(message)
        if (delay_seconds is None) == (run_at is None):
            raise AutomationValidationError(
                "Indiquez soit delay_seconds, soit run_at, mais pas les deux."
            )

        now = datetime.now(timezone.utc)
        if delay_seconds is not None:
            delay = self.validate_delay(delay_seconds)
            target = now + timedelta(seconds=delay)
        else:
            target = self.parse_run_at(run_at)
            if target <= now:
                raise AutomationValidationError("La date du rappel doit être dans le futur.")

        task = self.repository.create_reminder(message=clean_message, run_at=target)
        self.logger.info("Rappel planifié #%d pour %s.", task.id, task.run_at.isoformat())
        self.events.publish("automation.scheduled", task.to_dict())
        return task

    def list(self, *, status: str | None = "pending", limit: int = 100) -> list[ScheduledTask]:
        if status is not None and status not in self.STATUSES:
            raise AutomationValidationError("Statut d'automatisation invalide.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise AutomationValidationError("La limite doit être comprise entre 1 et 200.")
        return self.repository.list(status=status, limit=limit)

    def cancel(self, task_id: int) -> bool:
        self.validate_task_id(task_id)
        cancelled = self.repository.cancel(task_id)
        if cancelled:
            self.logger.info("Automatisation #%d annulée.", task_id)
            self.events.publish("automation.cancelled", {"id": task_id})
        return cancelled

    async def run(self, *, interval: float = 1.0) -> None:
        self.logger.info("Scheduler SIDERON démarré.")
        try:
            while True:
                now = datetime.now(timezone.utc)
                for task in self.repository.due(now):
                    if not self.repository.complete(task.id, now):
                        continue
                    payload = task.to_dict()
                    payload["status"] = "completed"
                    payload["completed_at"] = now.isoformat()
                    self.logger.info("Rappel arrivé à échéance #%d : %s", task.id, task.message)
                    self.events.publish("automation.reminder_due", payload)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            self.logger.info("Scheduler SIDERON arrêté.")
            raise

    @classmethod
    def validate_message(cls, value: str) -> str:
        if not isinstance(value, str):
            raise AutomationValidationError("Le texte du rappel doit être une chaîne.")
        cleaned = value.strip()
        if not cleaned:
            raise AutomationValidationError("Le texte du rappel ne peut pas être vide.")
        if len(cleaned) > cls.MAX_MESSAGE_LENGTH:
            raise AutomationValidationError(
                f"Le texte du rappel ne peut pas dépasser {cls.MAX_MESSAGE_LENGTH} caractères."
            )
        return cleaned

    @classmethod
    def validate_delay(cls, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise AutomationValidationError("delay_seconds doit être un entier.")
        if value < 1 or value > cls.MAX_DELAY_SECONDS:
            raise AutomationValidationError(
                f"delay_seconds doit être compris entre 1 et {cls.MAX_DELAY_SECONDS}."
            )
        return value

    @staticmethod
    def validate_task_id(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise AutomationValidationError("L'identifiant doit être un entier positif.")
        return value

    @staticmethod
    def parse_run_at(value: str | None) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise AutomationValidationError("run_at doit être une date ISO 8601.")
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise AutomationValidationError("run_at doit être une date ISO 8601 valide.") from exc
        if parsed.tzinfo is None:
            raise AutomationValidationError("run_at doit inclure un fuseau horaire.")
        return parsed.astimezone(timezone.utc)
