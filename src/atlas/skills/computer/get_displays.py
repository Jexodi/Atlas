from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any

from atlas.security.risk import RiskLevel
from atlas.skills.base import Skill, SkillResult


MONITORINFOF_PRIMARY = 0x00000001
ENUM_CURRENT_SETTINGS = -1

DM_DISPLAYORIENTATION = 0x00000080
DM_DISPLAYFREQUENCY = 0x00400000
DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000


class RECT(
    ctypes.Structure
):

    _fields_ = [
        (
            "left",
            wintypes.LONG,
        ),
        (
            "top",
            wintypes.LONG,
        ),
        (
            "right",
            wintypes.LONG,
        ),
        (
            "bottom",
            wintypes.LONG,
        ),
    ]


class MONITORINFOEXW(
    ctypes.Structure
):

    _fields_ = [
        (
            "cbSize",
            wintypes.DWORD,
        ),
        (
            "rcMonitor",
            RECT,
        ),
        (
            "rcWork",
            RECT,
        ),
        (
            "dwFlags",
            wintypes.DWORD,
        ),
        (
            "szDevice",
            wintypes.WCHAR * 32,
        ),
    ]


class POINTL(
    ctypes.Structure
):

    _fields_ = [
        (
            "x",
            wintypes.LONG,
        ),
        (
            "y",
            wintypes.LONG,
        ),
    ]


class DEVMODEW(
    ctypes.Structure
):

    _fields_ = [
        (
            "dmDeviceName",
            wintypes.WCHAR * 32,
        ),
        (
            "dmSpecVersion",
            wintypes.WORD,
        ),
        (
            "dmDriverVersion",
            wintypes.WORD,
        ),
        (
            "dmSize",
            wintypes.WORD,
        ),
        (
            "dmDriverExtra",
            wintypes.WORD,
        ),
        (
            "dmFields",
            wintypes.DWORD,
        ),
        (
            "dmPosition",
            POINTL,
        ),
        (
            "dmDisplayOrientation",
            wintypes.DWORD,
        ),
        (
            "dmDisplayFixedOutput",
            wintypes.DWORD,
        ),
        (
            "dmColor",
            wintypes.SHORT,
        ),
        (
            "dmDuplex",
            wintypes.SHORT,
        ),
        (
            "dmYResolution",
            wintypes.SHORT,
        ),
        (
            "dmTTOption",
            wintypes.SHORT,
        ),
        (
            "dmCollate",
            wintypes.SHORT,
        ),
        (
            "dmFormName",
            wintypes.WCHAR * 32,
        ),
        (
            "dmLogPixels",
            wintypes.WORD,
        ),
        (
            "dmBitsPerPel",
            wintypes.DWORD,
        ),
        (
            "dmPelsWidth",
            wintypes.DWORD,
        ),
        (
            "dmPelsHeight",
            wintypes.DWORD,
        ),
        (
            "dmDisplayFlags",
            wintypes.DWORD,
        ),
        (
            "dmDisplayFrequency",
            wintypes.DWORD,
        ),
        (
            "dmICMMethod",
            wintypes.DWORD,
        ),
        (
            "dmICMIntent",
            wintypes.DWORD,
        ),
        (
            "dmMediaType",
            wintypes.DWORD,
        ),
        (
            "dmDitherType",
            wintypes.DWORD,
        ),
        (
            "dmReserved1",
            wintypes.DWORD,
        ),
        (
            "dmReserved2",
            wintypes.DWORD,
        ),
        (
            "dmPanningWidth",
            wintypes.DWORD,
        ),
        (
            "dmPanningHeight",
            wintypes.DWORD,
        ),
    ]


class GetComputerDisplaysSkill(Skill):

    name = "computer.get_displays"

    description = (
        "Récupère les écrans actifs de Windows avec leur position, "
        "résolution, zone de travail, fréquence et écran principal."
    )

    parameters = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    risk_level = RiskLevel.READ_ONLY

    required_permission = None

    requires_service = False

    def execute(
        self,
        **kwargs: Any,
    ) -> SkillResult:

        try:

            displays = self._enumerate_displays()

        except Exception as exc:

            return SkillResult(
                success=False,
                message=(
                    "Impossible de récupérer la configuration des écrans."
                ),
                data={
                    "error": str(exc),
                },
            )

        if not displays:

            return SkillResult(
                success=True,
                message=(
                    "Aucun écran actif n'a été détecté."
                ),
                data={
                    "displays": [],
                    "count": 0,
                    "primary_display": None,
                },
            )

        primary_display = next(
            (
                display
                for display in displays
                if display.get(
                    "primary"
                )
            ),
            None,
        )

        return SkillResult(
            success=True,
            message=(
                f"{len(displays)} écran(s) actif(s) détecté(s)."
            ),
            data={
                "displays": displays,
                "count": len(
                    displays
                ),
                "primary_display": (
                    primary_display
                ),
            },
        )

    def _enumerate_displays(
        self,
    ) -> list[dict[str, Any]]:

        user32 = ctypes.windll.user32

        monitor_enum_proc = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HMONITOR,
            wintypes.HDC,
            ctypes.POINTER(
                RECT
            ),
            wintypes.LPARAM,
        )

        displays: list[
            dict[str, Any]
        ] = []

        def callback(
            monitor_handle,
            device_context,
            monitor_rect,
            data,
        ):

            monitor_info = (
                MONITORINFOEXW()
            )

            monitor_info.cbSize = (
                ctypes.sizeof(
                    MONITORINFOEXW
                )
            )

            if not user32.GetMonitorInfoW(
                monitor_handle,
                ctypes.byref(
                    monitor_info
                ),
            ):

                return True

            monitor_bounds = (
                monitor_info.rcMonitor
            )

            work_bounds = (
                monitor_info.rcWork
            )

            device_name = (
                monitor_info.szDevice
            )

            devmode = DEVMODEW()

            devmode.dmSize = (
                ctypes.sizeof(
                    DEVMODEW
                )
            )

            has_display_settings = bool(
                user32.EnumDisplaySettingsW(
                    device_name,
                    ENUM_CURRENT_SETTINGS,
                    ctypes.byref(
                        devmode
                    ),
                )
            )

            orientation = None
            refresh_rate_hz = None

            if has_display_settings:

                orientation = (
                    self._orientation_name(
                        int(
                            devmode.dmDisplayOrientation
                        )
                    )
                )

                if (
                    devmode.dmDisplayFrequency
                    > 1
                ):

                    refresh_rate_hz = int(
                        devmode.dmDisplayFrequency
                    )

            width = (
                monitor_bounds.right
                - monitor_bounds.left
            )

            height = (
                monitor_bounds.bottom
                - monitor_bounds.top
            )

            work_width = (
                work_bounds.right
                - work_bounds.left
            )

            work_height = (
                work_bounds.bottom
                - work_bounds.top
            )

            displays.append(
                {
                    "index": (
                        len(displays)
                        + 1
                    ),
                    "device_name": (
                        device_name
                    ),
                    "primary": bool(
                        monitor_info.dwFlags
                        & MONITORINFOF_PRIMARY
                    ),
                    "x": (
                        monitor_bounds.left
                    ),
                    "y": (
                        monitor_bounds.top
                    ),
                    "width": width,
                    "height": height,
                    "resolution": (
                        f"{width}x{height}"
                    ),
                    "bounds": {
                        "left": (
                            monitor_bounds.left
                        ),
                        "top": (
                            monitor_bounds.top
                        ),
                        "right": (
                            monitor_bounds.right
                        ),
                        "bottom": (
                            monitor_bounds.bottom
                        ),
                    },
                    "work_area": {
                        "left": (
                            work_bounds.left
                        ),
                        "top": (
                            work_bounds.top
                        ),
                        "right": (
                            work_bounds.right
                        ),
                        "bottom": (
                            work_bounds.bottom
                        ),
                        "width": (
                            work_width
                        ),
                        "height": (
                            work_height
                        ),
                    },
                    "refresh_rate_hz": (
                        refresh_rate_hz
                    ),
                    "orientation": (
                        orientation
                    ),
                }
            )

            return True

        callback_reference = (
            monitor_enum_proc(
                callback
            )
        )

        if not user32.EnumDisplayMonitors(
            0,
            None,
            callback_reference,
            0,
        ):

            raise OSError(
                "EnumDisplayMonitors a échoué."
            )

        displays.sort(
            key=lambda display: (
                display[
                    "x"
                ],
                display[
                    "y"
                ],
            )
        )

        for index, display in enumerate(
            displays,
            start=1,
        ):

            display[
                "index"
            ] = index

        return displays

    @staticmethod
    def _orientation_name(
        value: int,
    ) -> str:

        names = {
            0: "landscape",
            1: "portrait",
            2: "landscape_flipped",
            3: "portrait_flipped",
        }

        return names.get(
            value,
            "unknown",
        )
