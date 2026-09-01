from __future__ import annotations

import asyncio
from typing import Any

from atlas.core.event_bus import EventBus

from .models import SystemEventSnapshot


class SystemEventManager:
    """Détecte les changements système et les publie sur l'EventBus SIDERON."""

    def __init__(
        self,
        *,
        provider,
        event_bus: EventBus,
        logger,
        disk_low_threshold_percent: float = 10.0,
    ) -> None:
        self.provider = provider
        self.events = event_bus
        self.logger = logger
        self.disk_low_threshold_percent = max(1.0, min(50.0, float(disk_low_threshold_percent)))
        self._previous: SystemEventSnapshot | None = None
        self._disk_low = False

    def poll(self) -> SystemEventSnapshot:
        current = self.provider.collect()
        previous = self._previous

        if previous is None:
            self._previous = current
            self._disk_low = current.disk_free_percent <= self.disk_low_threshold_percent
            return current

        self._detect_network(previous, current)
        self._detect_session(previous, current)
        self._detect_audio(previous, current)
        self._detect_battery(previous, current)
        self._detect_disk(current)

        self._previous = current
        return current

    async def run(self, *, interval: float = 5.0) -> None:
        self.logger.info("Surveillance des événements système démarrée.")
        try:
            while True:
                try:
                    self.poll()
                except Exception:
                    self.logger.exception("Impossible de collecter les événements système.")
                await asyncio.sleep(max(1.0, float(interval)))
        except asyncio.CancelledError:
            self.logger.info("Surveillance des événements système arrêtée.")
            raise

    def _emit(self, event_name: str, payload: dict[str, Any]) -> None:
        data = dict(payload)
        self.events.publish(event_name, data)
        self.events.publish(
            "system.event",
            {
                "type": event_name,
                **data,
            },
        )

    def _detect_network(self, previous: SystemEventSnapshot, current: SystemEventSnapshot) -> None:
        if current.network_connected != previous.network_connected:
            self._emit(
                "system.network_connected" if current.network_connected else "system.network_disconnected",
                {
                    "connected": current.network_connected,
                    "interfaces": list(current.network_interfaces),
                },
            )
        elif current.network_interfaces != previous.network_interfaces:
            self._emit(
                "system.network_interfaces_changed",
                {
                    "connected": current.network_connected,
                    "previous": list(previous.network_interfaces),
                    "current": list(current.network_interfaces),
                },
            )

    def _detect_session(self, previous: SystemEventSnapshot, current: SystemEventSnapshot) -> None:
        if current.session_locked is None or previous.session_locked is None:
            return
        if current.session_locked == previous.session_locked:
            return
        self._emit(
            "system.session_locked" if current.session_locked else "system.session_unlocked",
            {"locked": current.session_locked},
        )

    def _detect_audio(self, previous: SystemEventSnapshot, current: SystemEventSnapshot) -> None:
        if (
            current.audio_inputs == previous.audio_inputs
            and current.audio_outputs == previous.audio_outputs
        ):
            return

        previous_inputs = set(previous.audio_inputs)
        current_inputs = set(current.audio_inputs)
        previous_outputs = set(previous.audio_outputs)
        current_outputs = set(current.audio_outputs)

        self._emit(
            "system.audio_devices_changed",
            {
                "inputs_added": sorted(current_inputs - previous_inputs),
                "inputs_removed": sorted(previous_inputs - current_inputs),
                "outputs_added": sorted(current_outputs - previous_outputs),
                "outputs_removed": sorted(previous_outputs - current_outputs),
            },
        )

    @staticmethod
    def _battery_bucket(percent: float | None) -> int | None:
        if percent is None:
            return None
        if percent <= 10:
            return 10
        if percent <= 20:
            return 20
        if percent <= 50:
            return 50
        return 100

    def _detect_battery(self, previous: SystemEventSnapshot, current: SystemEventSnapshot) -> None:
        if current.battery_percent is None:
            return

        plugged_changed = (
            previous.battery_plugged is not None
            and current.battery_plugged != previous.battery_plugged
        )
        bucket_changed = self._battery_bucket(current.battery_percent) != self._battery_bucket(previous.battery_percent)

        if not plugged_changed and not bucket_changed:
            return

        self._emit(
            "system.battery_changed",
            {
                "percent": current.battery_percent,
                "plugged": current.battery_plugged,
            },
        )

    def _detect_disk(self, current: SystemEventSnapshot) -> None:
        threshold = self.disk_low_threshold_percent
        if not self._disk_low and current.disk_free_percent <= threshold:
            self._disk_low = True
            self._emit(
                "system.disk_space_low",
                {
                    "free_percent": current.disk_free_percent,
                    "threshold_percent": threshold,
                },
            )
            return

        # Hystérésis de 2 points pour éviter les bascules répétées autour du seuil.
        if self._disk_low and current.disk_free_percent >= threshold + 2.0:
            self._disk_low = False
            self._emit(
                "system.disk_space_recovered",
                {
                    "free_percent": current.disk_free_percent,
                    "threshold_percent": threshold,
                },
            )
