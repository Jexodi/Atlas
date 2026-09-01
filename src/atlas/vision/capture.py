from __future__ import annotations

import ctypes
import os
import struct
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ActiveWindowCapture:
    path: Path
    title: str | None
    process_id: int | None
    width: int
    height: int


class ActiveWindowCaptureError(RuntimeError):
    pass


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BITMAPINFOHEADER),
        ("bmiColors", ctypes.c_uint32 * 3),
    ]


class ActiveWindowCapturer:
    SRCCOPY = 0x00CC0020
    CAPTUREBLT = 0x40000000
    BI_RGB = 0
    DIB_RGB_COLORS = 0
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    HALFTONE = 4
    MAX_CAPTURE_WIDTH = 1600
    MAX_CAPTURE_HEIGHT = 1200

    def capture(self, output_dir: str | Path) -> ActiveWindowCapture:
        if os.name != "nt":
            raise ActiveWindowCaptureError("La capture de fenêtre active nécessite Windows.")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            raise ActiveWindowCaptureError("Aucune fenêtre active n'a été trouvée.")
        if user32.IsIconic(hwnd):
            raise ActiveWindowCaptureError("La fenêtre active est minimisée et ne peut pas être capturée.")

        rect = _RECT()
        hr = dwmapi.DwmGetWindowAttribute(
            ctypes.c_void_p(hwnd),
            self.DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(rect),
            ctypes.sizeof(rect),
        )
        if hr != 0:
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                raise ActiveWindowCaptureError("Impossible de déterminer les dimensions de la fenêtre active.")

        source_width = int(rect.right - rect.left)
        source_height = int(rect.bottom - rect.top)
        if source_width <= 0 or source_height <= 0:
            raise ActiveWindowCaptureError("La fenêtre active a des dimensions invalides.")

        scale = min(
            1.0,
            self.MAX_CAPTURE_WIDTH / source_width,
            self.MAX_CAPTURE_HEIGHT / source_height,
        )
        width = max(1, int(round(source_width * scale)))
        height = max(1, int(round(source_height * scale)))

        title_len = user32.GetWindowTextLengthW(hwnd)
        title_buffer = ctypes.create_unicode_buffer(title_len + 1)
        user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
        title = title_buffer.value or None

        pid = ctypes.c_uint32(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_id = int(pid.value) or None

        screen_dc = user32.GetDC(None)
        if not screen_dc:
            raise ActiveWindowCaptureError("Impossible d'accéder au bureau Windows pour la capture.")

        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        if not mem_dc:
            user32.ReleaseDC(None, screen_dc)
            raise ActiveWindowCaptureError("Impossible de créer le contexte graphique de capture.")

        bits = ctypes.c_void_p()
        info = _BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = self.BI_RGB

        bitmap = gdi32.CreateDIBSection(
            screen_dc,
            ctypes.byref(info),
            self.DIB_RGB_COLORS,
            ctypes.byref(bits),
            None,
            0,
        )
        if not bitmap or not bits.value:
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(None, screen_dc)
            raise ActiveWindowCaptureError("Impossible de créer le tampon d'image de capture.")

        previous = gdi32.SelectObject(mem_dc, bitmap)
        try:
            gdi32.SetStretchBltMode(mem_dc, self.HALFTONE)
            ok = gdi32.StretchBlt(
                mem_dc,
                0,
                0,
                width,
                height,
                screen_dc,
                rect.left,
                rect.top,
                source_width,
                source_height,
                self.SRCCOPY | self.CAPTUREBLT,
            )
            if not ok:
                raise ActiveWindowCaptureError("La capture graphique de la fenêtre active a échoué.")

            bgra = ctypes.string_at(bits.value, width * height * 4)
        finally:
            if previous:
                gdi32.SelectObject(mem_dc, previous)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(None, screen_dc)

        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        filename = "active-window-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".png"
        path = output / filename
        self._write_png(path, width, height, bgra)

        return ActiveWindowCapture(
            path=path,
            title=title,
            process_id=process_id,
            width=width,
            height=height,
        )

    @staticmethod
    def _write_png(path: Path, width: int, height: int, bgra: bytes) -> None:
        rows = bytearray()
        stride = width * 4
        for y in range(height):
            rows.append(0)
            row = bgra[y * stride:(y + 1) * stride]
            for x in range(0, len(row), 4):
                b, g, r, _a = row[x:x + 4]
                rows.extend((r, g, b))

        def chunk(kind: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + kind
                + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
            )

        png = bytearray(b"\x89PNG\r\n\x1a\n")
        png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(bytes(rows), level=6))
        png += chunk(b"IEND", b"")
        path.write_bytes(png)
