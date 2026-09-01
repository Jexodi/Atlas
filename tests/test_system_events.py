from __future__ import annotations

from atlas.core.event_bus import EventBus
from atlas.system_events import SystemEventManager, SystemEventSnapshot


class LoggerStub:
    def info(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


class SequenceProvider:
    def __init__(self, *snapshots: SystemEventSnapshot):
        self.snapshots = list(snapshots)

    def collect(self) -> SystemEventSnapshot:
        if len(self.snapshots) > 1:
            return self.snapshots.pop(0)
        return self.snapshots[0]


def make_manager(*snapshots, threshold=10.0):
    events = EventBus()
    manager = SystemEventManager(
        provider=SequenceProvider(*snapshots),
        event_bus=events,
        logger=LoggerStub(),
        disk_low_threshold_percent=threshold,
    )
    received = []
    events.subscribe("system.event", received.append)
    return manager, received


def test_first_poll_establishes_baseline_without_event():
    snapshot = SystemEventSnapshot(network_connected=True, network_interfaces=("Ethernet",))
    manager, received = make_manager(snapshot)

    manager.poll()

    assert received == []


def test_network_disconnect_and_reconnect_are_emitted():
    connected = SystemEventSnapshot(network_connected=True, network_interfaces=("Ethernet",))
    disconnected = SystemEventSnapshot(network_connected=False, network_interfaces=())
    manager, received = make_manager(connected, disconnected, connected)

    manager.poll()
    manager.poll()
    manager.poll()

    assert [item["type"] for item in received] == [
        "system.network_disconnected",
        "system.network_connected",
    ]


def test_session_lock_and_unlock_are_emitted():
    unlocked = SystemEventSnapshot(session_locked=False)
    locked = SystemEventSnapshot(session_locked=True)
    manager, received = make_manager(unlocked, locked, unlocked)

    manager.poll()
    manager.poll()
    manager.poll()

    assert [item["type"] for item in received] == [
        "system.session_locked",
        "system.session_unlocked",
    ]


def test_audio_device_changes_report_added_and_removed_devices():
    before = SystemEventSnapshot(
        audio_inputs=("Mic A",),
        audio_outputs=("Speakers A",),
    )
    after = SystemEventSnapshot(
        audio_inputs=("Mic B",),
        audio_outputs=("Speakers A", "Headset B"),
    )
    manager, received = make_manager(before, after)

    manager.poll()
    manager.poll()

    event = received[0]
    assert event["type"] == "system.audio_devices_changed"
    assert event["inputs_added"] == ["Mic B"]
    assert event["inputs_removed"] == ["Mic A"]
    assert event["outputs_added"] == ["Headset B"]
    assert event["outputs_removed"] == []


def test_disk_low_event_uses_hysteresis_before_recovery():
    normal = SystemEventSnapshot(disk_free_percent=15.0)
    low = SystemEventSnapshot(disk_free_percent=9.0)
    still_low = SystemEventSnapshot(disk_free_percent=11.0)
    recovered = SystemEventSnapshot(disk_free_percent=12.5)
    manager, received = make_manager(normal, low, still_low, recovered, threshold=10.0)

    manager.poll()
    manager.poll()
    manager.poll()
    manager.poll()

    assert [item["type"] for item in received] == [
        "system.disk_space_low",
        "system.disk_space_recovered",
    ]


def test_battery_event_only_on_meaningful_change():
    start = SystemEventSnapshot(battery_percent=80.0, battery_plugged=True)
    small_change = SystemEventSnapshot(battery_percent=79.0, battery_plugged=True)
    unplugged = SystemEventSnapshot(battery_percent=78.0, battery_plugged=False)
    low = SystemEventSnapshot(battery_percent=19.0, battery_plugged=False)
    manager, received = make_manager(start, small_change, unplugged, low)

    manager.poll()
    manager.poll()
    manager.poll()
    manager.poll()

    assert [item["type"] for item in received] == [
        "system.battery_changed",
        "system.battery_changed",
    ]


def test_audio_state_prefers_windows_mmdevices_over_portaudio(monkeypatch, tmp_path):
    from atlas.system_events.provider import SystemEventSnapshotProvider

    class AudioDevicesShouldNotBeCalled:
        def device_choices(self, refresh=False):
            raise AssertionError("PortAudio ne doit pas être interrogé quand MMDevices est disponible")

    provider = SystemEventSnapshotProvider(
        storage_root=tmp_path,
        audio_devices=AudioDevicesShouldNotBeCalled(),
    )
    monkeypatch.setattr(
        provider,
        "_windows_audio_state",
        lambda: (("MMDEVICE::capture::mic",), ("MMDEVICE::render::speaker",)),
    )

    assert provider._audio_state() == (
        ("MMDEVICE::capture::mic",),
        ("MMDEVICE::render::speaker",),
    )


def test_audio_state_falls_back_to_portaudio_when_mmdevices_unavailable(monkeypatch, tmp_path):
    from atlas.system_events.provider import SystemEventSnapshotProvider

    class AudioDevicesStub:
        def device_choices(self, refresh=False):
            assert refresh is True
            return {
                "inputs": [{"id": "Mic A"}],
                "outputs": [{"id": "Speaker A"}],
            }

    provider = SystemEventSnapshotProvider(
        storage_root=tmp_path,
        audio_devices=AudioDevicesStub(),
    )
    monkeypatch.setattr(provider, "_windows_audio_state", lambda: None)

    assert provider._audio_state() == (("Mic A",), ("Speaker A",))
