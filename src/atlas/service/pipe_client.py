from __future__ import annotations

import ctypes
import os
import time

from ctypes import wintypes

from atlas.service.pipe_security import (
    CLIENT_PIPE_ACCESS_MASK,
)

from atlas.service.protocol import (
    MAX_MESSAGE_SIZE,
    PIPE_ADDRESS,
)


# =========================================================
# Constantes Windows
# =========================================================

OPEN_EXISTING = 3

PIPE_READMODE_MESSAGE = 0x00000002

ERROR_FILE_NOT_FOUND = 2
ERROR_ACCESS_DENIED = 5
ERROR_PIPE_BUSY = 231
ERROR_MORE_DATA = 234

INVALID_HANDLE_VALUE = (
    ctypes.c_void_p(
        -1
    ).value
)


# =========================================================
# DLL
# =========================================================

kernel32 = ctypes.WinDLL(
    "kernel32",
    use_last_error=True,
)


# =========================================================
# Prototypes
# =========================================================


kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]

kernel32.CreateFileW.restype = (
    wintypes.HANDLE
)


kernel32.WaitNamedPipeW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
]

kernel32.WaitNamedPipeW.restype = (
    wintypes.BOOL
)


kernel32.SetNamedPipeHandleState.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(
        wintypes.DWORD
    ),
    ctypes.POINTER(
        wintypes.DWORD
    ),
    ctypes.POINTER(
        wintypes.DWORD
    ),
]

kernel32.SetNamedPipeHandleState.restype = (
    wintypes.BOOL
)


kernel32.WriteFile.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.DWORD,
    ctypes.POINTER(
        wintypes.DWORD
    ),
    wintypes.LPVOID,
]

kernel32.WriteFile.restype = (
    wintypes.BOOL
)


kernel32.ReadFile.argtypes = [
    wintypes.HANDLE,
    wintypes.LPVOID,
    wintypes.DWORD,
    ctypes.POINTER(
        wintypes.DWORD
    ),
    wintypes.LPVOID,
]

kernel32.ReadFile.restype = (
    wintypes.BOOL
)


kernel32.CloseHandle.argtypes = [
    wintypes.HANDLE,
]

kernel32.CloseHandle.restype = (
    wintypes.BOOL
)


# =========================================================
# Exceptions
# =========================================================


class PipeClientError(
    RuntimeError
):
    pass


class PipeUnavailableError(
    PipeClientError
):
    pass


class PipeAccessDeniedError(
    PipeClientError
):
    pass


# =========================================================
# Client
# =========================================================


class WindowsNamedPipeClient:

    def __init__(
        self,
        timeout_seconds: float = 5.0,
    ) -> None:

        self.timeout_seconds = (
            timeout_seconds
        )

    # =====================================================
    # Connexion
    # =====================================================

    def _connect(
        self,
    ) -> wintypes.HANDLE:

        if os.name != "nt":

            raise PipeClientError(
                "SideronService est disponible "
                "uniquement sous Windows."
            )

        deadline = (
            time.monotonic()
            + self.timeout_seconds
        )

        while True:

            handle = (
                kernel32.CreateFileW(
                    PIPE_ADDRESS,

                    # Droits spécifiques uniquement.
                    CLIENT_PIPE_ACCESS_MASK,

                    0,
                    None,
                    OPEN_EXISTING,
                    0,
                    None,
                )
            )

            if (
                handle
                != INVALID_HANDLE_VALUE
            ):

                mode = (
                    wintypes.DWORD(
                        PIPE_READMODE_MESSAGE
                    )
                )

                if not (
                    kernel32
                    .SetNamedPipeHandleState(
                        handle,
                        ctypes.byref(
                            mode
                        ),
                        None,
                        None,
                    )
                ):

                    error = (
                        ctypes.get_last_error()
                    )

                    kernel32.CloseHandle(
                        handle
                    )

                    raise PipeClientError(
                        "Impossible de configurer "
                        "le Named Pipe : "
                        f"{ctypes.WinError(error)}"
                    )

                return handle

            error = (
                ctypes.get_last_error()
            )

            # =================================================
            # Accès refusé
            # =================================================

            if (
                error
                == ERROR_ACCESS_DENIED
            ):

                raise PipeAccessDeniedError(
                    "Accès refusé au Named Pipe "
                    "SideronService."
                )

            # =================================================
            # Pipe occupé
            # =================================================

            if (
                error
                == ERROR_PIPE_BUSY
            ):

                remaining = (
                    deadline
                    - time.monotonic()
                )

                if remaining <= 0:

                    raise PipeUnavailableError(
                        "SideronService est occupé "
                        "ou ne répond pas."
                    )

                wait_ms = max(
                    1,
                    int(
                        remaining
                        * 1000
                    ),
                )

                kernel32.WaitNamedPipeW(
                    PIPE_ADDRESS,
                    wait_ms,
                )

                continue

            # =================================================
            # Pipe inexistant
            # =================================================

            if (
                error
                == ERROR_FILE_NOT_FOUND
            ):

                if (
                    time.monotonic()
                    >= deadline
                ):

                    raise PipeUnavailableError(
                        "SideronService n'est pas "
                        "disponible."
                    )

                time.sleep(
                    0.1
                )

                continue

            raise PipeClientError(
                "Impossible de se connecter "
                "à SideronService : "
                f"{ctypes.WinError(error)}"
            )

    # =====================================================
    # Write
    # =====================================================

    def _write(
        self,
        handle: wintypes.HANDLE,
        payload: bytes,
    ) -> None:

        if len(payload) > MAX_MESSAGE_SIZE:

            raise PipeClientError(
                "Message SideronService "
                "trop volumineux."
            )

        buffer = (
            ctypes.create_string_buffer(
                payload
            )
        )

        written = (
            wintypes.DWORD(
                0
            )
        )

        if not kernel32.WriteFile(
            handle,
            buffer,
            len(payload),
            ctypes.byref(
                written
            ),
            None,
        ):

            raise PipeClientError(
                "Échec d'écriture dans "
                "SideronService : "
                f"{ctypes.WinError(ctypes.get_last_error())}"
            )

        if (
            written.value
            != len(payload)
        ):

            raise PipeClientError(
                "Message SideronService "
                "partiellement envoyé."
            )

    # =====================================================
    # Read
    # =====================================================

    def _read(
        self,
        handle: wintypes.HANDLE,
    ) -> bytes:

        buffer = (
            ctypes.create_string_buffer(
                MAX_MESSAGE_SIZE
            )
        )

        read = (
            wintypes.DWORD(
                0
            )
        )

        success = (
            kernel32.ReadFile(
                handle,
                buffer,
                MAX_MESSAGE_SIZE,
                ctypes.byref(
                    read
                ),
                None,
            )
        )

        if not success:

            error = (
                ctypes.get_last_error()
            )

            if (
                error
                == ERROR_MORE_DATA
            ):

                raise PipeClientError(
                    "Réponse SideronService "
                    "trop volumineuse."
                )

            raise PipeClientError(
                "Échec de lecture depuis "
                "SideronService : "
                f"{ctypes.WinError(error)}"
            )

        return bytes(
            buffer.raw[
                :read.value
            ]
        )

    # =====================================================
    # Exchange
    # =====================================================

    def exchange(
        self,
        payload: bytes,
    ) -> bytes:

        handle = (
            self._connect()
        )

        try:

            self._write(
                handle,
                payload,
            )

            return self._read(
                handle
            )

        finally:

            kernel32.CloseHandle(
                handle
            )