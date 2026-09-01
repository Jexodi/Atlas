from __future__ import annotations

import ctypes
import os
import shutil
import socket
from pathlib import Path
from typing import TYPE_CHECKING

import psutil

if TYPE_CHECKING:
    from atlas.audio.devices import AudioDeviceManager

from .models import SystemEventSnapshot


class SystemEventSnapshotProvider:
    """Collecte locale de signaux système, sans dépendance à OpenAI."""

    DESKTOP_SWITCHDESKTOP = 0x0100
    _MMDEVICE_ROOT = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio"
    _MMDEVICE_ACTIVE = 0x00000001

    def __init__(
        self,
        *,
        storage_root: str | Path,
        audio_devices: AudioDeviceManager | None = None,
    ) -> None:
        self.storage_root = Path(storage_root)
        self.audio_devices = audio_devices

    def collect(self) -> SystemEventSnapshot:
        network_connected, interfaces = self._network_state()
        battery_percent, battery_plugged = self._battery_state()
        audio_inputs, audio_outputs = self._audio_state()

        return SystemEventSnapshot(
            network_connected=network_connected,
            network_interfaces=interfaces,
            session_locked=self._session_locked(),
            battery_percent=battery_percent,
            battery_plugged=battery_plugged,
            disk_free_percent=self._disk_free_percent(),
            audio_inputs=audio_inputs,
            audio_outputs=audio_outputs,
        )

    @staticmethod
    def _network_state() -> tuple[bool, tuple[str, ...]]:
        stats = psutil.net_if_stats()
        addresses = psutil.net_if_addrs()
        active: list[str] = []

        for name, interface_stats in stats.items():
            if not interface_stats.isup:
                continue

            has_usable_ipv4 = False
            for address in addresses.get(name, ()):  # pragma: no branch - petit parcours
                if address.family != socket.AF_INET:
                    continue
                ip = str(address.address or "")
                if not ip or ip.startswith("127.") or ip.startswith("169.254."):
                    continue
                has_usable_ipv4 = True
                break

            if has_usable_ipv4:
                active.append(name)

        active.sort(key=str.casefold)
        return bool(active), tuple(active)

    @staticmethod
    def _battery_state() -> tuple[float | None, bool | None]:
        try:
            battery = psutil.sensors_battery()
        except (AttributeError, OSError):
            battery = None

        if battery is None:
            return None, None

        return round(float(battery.percent), 1), bool(battery.power_plugged)

    def _disk_free_percent(self) -> float:
        usage = shutil.disk_usage(self.storage_root)
        if usage.total <= 0:
            return 100.0
        return round((usage.free / usage.total) * 100.0, 2)

    def _audio_state(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        # PortAudio peut conserver un inventaire obsolète dans un processus
        # audio long-lived sous Windows. Pour la détection hot-plug, la source
        # de vérité est donc MMDevices dans le registre Windows. Cette lecture
        # est locale, non privilégiée et n'interrompt jamais le flux audio.
        windows_state = self._windows_audio_state()
        if windows_state is not None:
            return windows_state

        # Repli multi-plateforme et tests : réutilise l'inventaire audio
        # existant lorsqu'on n'est pas sous Windows ou si MMDevices est
        # indisponible.
        if self.audio_devices is None:
            return (), ()

        try:
            choices = self.audio_devices.device_choices(refresh=True)
        except Exception:
            return (), ()

        inputs = tuple(sorted(str(item.get("id", "")) for item in choices["inputs"] if item.get("id")))
        outputs = tuple(sorted(str(item.get("id", "")) for item in choices["outputs"] if item.get("id")))
        return inputs, outputs

    @classmethod
    def _windows_audio_state(cls) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
        if os.name != "nt":
            return None

        try:
            import winreg
        except ImportError:
            return None

        try:
            captures = cls._active_mmdevice_ids(
                winreg,
                rf"{cls._MMDEVICE_ROOT}\Capture",
                "capture",
            )
            renders = cls._active_mmdevice_ids(
                winreg,
                rf"{cls._MMDEVICE_ROOT}\Render",
                "render",
            )
        except OSError:
            # Une politique d'entreprise ou un Windows ancien peut empêcher
            # l'accès à MMDevices. Dans ce cas, le repli PortAudio reste
            # disponible plutôt que de casser le moniteur système.
            return None

        return captures, renders

    @classmethod
    def _active_mmdevice_ids(
        cls,
        winreg_module,
        registry_path: str,
        direction: str,
    ) -> tuple[str, ...]:
        active: list[str] = []

        with winreg_module.OpenKey(
            winreg_module.HKEY_LOCAL_MACHINE,
            registry_path,
            0,
            winreg_module.KEY_READ,
        ) as root:
            index = 0
            while True:
                try:
                    endpoint_id = winreg_module.EnumKey(root, index)
                except OSError:
                    break
                index += 1

                try:
                    with winreg_module.OpenKey(root, endpoint_id) as endpoint:
                        state, _ = winreg_module.QueryValueEx(endpoint, "DeviceState")
                except OSError:
                    continue

                if int(state) != cls._MMDEVICE_ACTIVE:
                    continue

                active.append(f"MMDEVICE::{direction}::{endpoint_id}")

        active.sort(key=str.casefold)
        return tuple(active)

    @classmethod
    def _session_locked(cls) -> bool | None:
        if os.name != "nt":
            return None

        try:
            user32 = ctypes.windll.user32
            handle = user32.OpenInputDesktop(0, False, cls.DESKTOP_SWITCHDESKTOP)
            if not handle:
                return True
            try:
                return not bool(user32.SwitchDesktop(handle))
            finally:
                user32.CloseDesktop(handle)
        except Exception:
            return None
