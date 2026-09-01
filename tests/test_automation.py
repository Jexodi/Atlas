from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from atlas.automation import AutomationManager, AutomationValidationError
from atlas.core.event_bus import EventBus


class LoggerStub:
    def info(self, *args, **kwargs):
        pass


def make_manager(tmp_path):
    events = EventBus()
    manager = AutomationManager(
        tmp_path / "sideron-automation.db",
        event_bus=events,
        logger=LoggerStub(),
    )
    manager.initialize()
    return manager, events


def test_create_relative_reminder_is_persistent(tmp_path):
    manager, _ = make_manager(tmp_path)
    task = manager.create_reminder(message="Tester SIDERON", delay_seconds=60)

    reloaded, _ = make_manager(tmp_path)
    pending = reloaded.list(status="pending")

    assert task.id == pending[0].id
    assert pending[0].message == "Tester SIDERON"
    assert pending[0].status == "pending"


def test_absolute_reminder_requires_timezone(tmp_path):
    manager, _ = make_manager(tmp_path)
    with pytest.raises(AutomationValidationError):
        manager.create_reminder(
            message="Test",
            run_at=(datetime.now() + timedelta(minutes=5)).isoformat(),
        )


def test_cancel_pending_reminder(tmp_path):
    manager, _ = make_manager(tmp_path)
    task = manager.create_reminder(message="Annuler", delay_seconds=60)

    assert manager.cancel(task.id) is True
    assert manager.list(status="pending") == []
    assert manager.list(status="cancelled")[0].id == task.id


def test_scheduler_emits_due_event_and_completes(tmp_path):
    manager, events = make_manager(tmp_path)
    received = []
    events.subscribe("automation.reminder_due", received.append)

    task = manager.repository.create_reminder(
        message="Échéance",
        run_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    async def scenario():
        runner = asyncio.create_task(manager.run(interval=0.01))
        try:
            for _ in range(100):
                if received:
                    break
                await asyncio.sleep(0.01)
        finally:
            runner.cancel()
            with pytest.raises(asyncio.CancelledError):
                await runner

    asyncio.run(scenario())

    assert received
    assert received[0]["id"] == task.id
    assert received[0]["message"] == "Échéance"
    assert manager.repository.get(task.id).status == "completed"
