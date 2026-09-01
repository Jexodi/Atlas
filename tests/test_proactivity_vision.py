from __future__ import annotations

from atlas.core.event_bus import EventBus
from atlas.proactivity import ProactivityManager
from atlas.vision import VisionPolicy


class LoggerStub:
    def info(self, *args, **kwargs):
        pass


class Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


def test_disk_low_creates_suggestion_without_action():
    events = EventBus()
    received = []
    events.subscribe("proactivity.suggestion", received.append)
    ProactivityManager(event_bus=events, logger=LoggerStub(), level="normal")

    events.publish("system.event", {"type": "system.disk_space_low", "free_percent": 8.5})

    assert len(received) == 1
    assert received[0]["source_event"] == "system.disk_space_low"
    assert "action" not in received[0]
    assert "command" not in received[0]


def test_off_level_emits_nothing():
    events = EventBus()
    received = []
    events.subscribe("proactivity.suggestion", received.append)
    ProactivityManager(event_bus=events, logger=LoggerStub(), level="off")

    events.publish("system.event", {"type": "system.disk_space_low", "free_percent": 8.5})

    assert received == []


def test_duplicate_suggestions_respect_cooldown():
    events = EventBus()
    clock = Clock()
    received = []
    events.subscribe("proactivity.suggestion", received.append)
    ProactivityManager(
        event_bus=events,
        logger=LoggerStub(),
        level="normal",
        cooldown_seconds=120,
        clock=clock,
    )

    payload = {"type": "system.disk_space_low", "free_percent": 8.5}
    events.publish("system.event", payload)
    events.publish("system.event", payload)
    assert len(received) == 1

    clock.value += 121
    events.publish("system.event", payload)
    assert len(received) == 2


def test_normal_level_does_not_interrupt_for_network_loss():
    events = EventBus()
    received = []
    events.subscribe("proactivity.suggestion", received.append)
    ProactivityManager(event_bus=events, logger=LoggerStub(), level="normal")

    events.publish("system.event", {"type": "system.network_disconnected"})

    assert received == []


def test_vision_policy_requires_explicit_basis():
    policy = VisionPolicy()

    assert policy.evaluate_capture().allowed is False
    assert policy.evaluate_capture(user_requested=True).allowed is True
    assert policy.evaluate_capture(explicit_permission=True).allowed is True
    assert policy.evaluate_capture(user_requested=True, privacy_mode=True).allowed is False


def test_audio_device_change_creates_normal_level_suggestion():
    events = EventBus()
    received = []
    events.subscribe("proactivity.suggestion", received.append)
    ProactivityManager(event_bus=events, logger=LoggerStub(), level="normal")

    events.publish(
        "system.event",
        {
            "type": "system.audio_devices_changed",
            "inputs_added": [],
            "inputs_removed": ["MMDEVICE::capture::mic"],
            "outputs_added": [],
            "outputs_removed": ["MMDEVICE::render::speaker"],
        },
    )

    assert len(received) == 1
    assert received[0]["source_event"] == "system.audio_devices_changed"
    assert received[0]["title"] == "Périphériques audio modifiés"
