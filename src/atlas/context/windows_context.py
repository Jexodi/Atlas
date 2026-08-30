import ctypes
from ctypes import wintypes

import psutil

from atlas.context.models import WindowContext


user32 = ctypes.windll.user32

kernel32 = ctypes.windll.kernel32


class WindowsContextProvider:

    def collect(self) -> WindowContext:

        hwnd = user32.GetForegroundWindow()

        if not hwnd:
            return WindowContext()

        title_length = user32.GetWindowTextLengthW(
            hwnd
        )

        title_buffer = ctypes.create_unicode_buffer(
            title_length + 1
        )

        user32.GetWindowTextW(
            hwnd,
            title_buffer,
            len(title_buffer),
        )

        process_id = wintypes.DWORD()

        user32.GetWindowThreadProcessId(
            hwnd,
            ctypes.byref(process_id),
        )

        process_name = None

        try:

            process = psutil.Process(
                process_id.value
            )

            process_name = process.name()

        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
        ):
            pass

        return WindowContext(
            active_window_title=(
                title_buffer.value or None
            ),
            active_process_name=process_name,
        )