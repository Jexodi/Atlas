from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SystemEventSnapshot:
    network_connected: bool = False
    network_interfaces: tuple[str, ...] = ()
    session_locked: bool | None = None
    battery_percent: float | None = None
    battery_plugged: bool | None = None
    disk_free_percent: float = 100.0
    audio_inputs: tuple[str, ...] = ()
    audio_outputs: tuple[str, ...] = ()
