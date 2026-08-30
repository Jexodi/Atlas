from __future__ import annotations

import ctypes
import os

from ctypes import wintypes
from threading import Event
from typing import Callable

from atlas.service.pipe_security import (
    create_pipe_security_attributes,
    free_security_descriptor,
    resolve_allowed_user_sid,
)

from atlas.service.protocol import (
    MAX_MESSAGE_SIZE,
    PIPE_ADDRESS,
)


# =========================================================
# Constantes
# =========================================================

PIPE_ACCESS_DUPLEX = 0x00000003

PIPE_TYPE_MESSAGE = 0x00000004
PIPE_READMODE_MESSAGE = 0x00000002
PIPE_WAIT = 0x00000000

PIPE_REJECT_REMOTE_CLIENTS = (
    0x00000008
)

ERROR_PIPE_CONNECTED = 535
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


kernel32.CreateNamedPipeW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
]

kernel32.CreateNamedPipeW.restype = (
    wintypes.HANDLE
)


kernel32.ConnectNamedPipe.argtypes = [
    wintypes.HANDLE,
    wintypes.LPVOID,
]

kernel32.ConnectNamedPipe.restype = (
    wintypes.BOOL
)


kernel32.DisconnectNamedPipe.argtypes = [
    wintypes.HANDLE,
]

kernel32.DisconnectNamedPipe.restype = (
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


kernel32.FlushFileBuffers.argtypes = [
    wintypes.HANDLE,
]

kernel32.FlushFileBuffers.restype = (
    wintypes.BOOL
)


kernel32.CloseHandle.argtypes = [
    wintypes.HANDLE,
]

kernel32.CloseHandle.restype = (
    wintypes.BOOL
)


# =========================================================
# Erreur
# =========================================================


class PipeServerError(
    RuntimeError
):
    pass


# =========================================================
# Serveur
# =========================================================


class SideronPipeServer:

    def __init__(
        self,
        allowed_user_sid: (
            str | None
        ) = None,
    ) -> None:

        if os.name != "nt":

            raise PipeServerError(
                "SideronService fonctionne "
                "uniquement sous Windows."
            )

        self.allowed_user_sid = (
            resolve_allowed_user_sid(
                allowed_user_sid
            )
        )

    # =====================================================
    # Création
    # =====================================================

    def _create_pipe(
        self,
    ) -> wintypes.HANDLE:

        (
            security_attributes,
            security_descriptor,
            _sddl,
        ) = (
            create_pipe_security_attributes(
                self.allowed_user_sid
            )
        )

        try:

            pipe_mode = (
                PIPE_TYPE_MESSAGE
                | PIPE_READMODE_MESSAGE
                | PIPE_WAIT
                | PIPE_REJECT_REMOTE_CLIENTS
            )

            handle = (
                kernel32.CreateNamedPipeW(
                    PIPE_ADDRESS,
                    PIPE_ACCESS_DUPLEX,
                    pipe_mode,
                    1,
                    MAX_MESSAGE_SIZE,
                    MAX_MESSAGE_SIZE,
                    5000,
                    ctypes.byref(
                        security_attributes
                    ),
                )
            )

        finally:

            free_security_descriptor(
                security_descriptor
            )

        if (
            handle
            == INVALID_HANDLE_VALUE
        ):

            raise PipeServerError(
                "Impossible de créer le "
                "Named Pipe SideronService : "
                f"{ctypes.WinError(ctypes.get_last_error())}"
            )

        return handle

    # =====================================================
    # Connexion
    # =====================================================

    def _wait_for_client(
        self,
        handle: wintypes.HANDLE,
    ) -> None:

        connected = (
            kernel32.ConnectNamedPipe(
                handle,
                None,
            )
        )

        if connected:

            return

        error = (
            ctypes.get_last_error()
        )

        if (
            error
            == ERROR_PIPE_CONNECTED
        ):

            return

        raise PipeServerError(
            "Impossible d'accepter le client "
            "Sideron : "
            f"{ctypes.WinError(error)}"
        )

    # =====================================================
    # Lecture
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

                raise PipeServerError(
                    "Requête Sideron trop volumineuse."
                )

            raise PipeServerError(
                "Lecture Named Pipe impossible : "
                f"{ctypes.WinError(error)}"
            )

        return bytes(
            buffer.raw[
                :read.value
            ]
        )

    # =====================================================
    # Écriture
    # =====================================================

    def _write(
        self,
        handle: wintypes.HANDLE,
        payload: bytes,
    ) -> None:

        if (
            len(payload)
            > MAX_MESSAGE_SIZE
        ):

            raise PipeServerError(
                "Réponse SideronService "
                "trop volumineuse."
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

            raise PipeServerError(
                "Écriture Named Pipe impossible : "
                f"{ctypes.WinError(ctypes.get_last_error())}"
            )

        if (
            written.value
            != len(payload)
        ):

            raise PipeServerError(
                "Réponse SideronService "
                "partiellement transmise."
            )

        kernel32.FlushFileBuffers(
            handle
        )

    # =====================================================
    # Boucle serveur
    # =====================================================

    def serve_forever(
        self,
        request_handler: Callable[
            [bytes],
            bytes,
        ],
        stop_event: (
            Event | None
        ) = None,
    ) -> None:

        while True:

            if (
                stop_event is not None
                and stop_event.is_set()
            ):

                return

            handle = (
                self._create_pipe()
            )

            try:

                self._wait_for_client(
                    handle
                )

                request = (
                    self._read(
                        handle
                    )
                )

                response = (
                    request_handler(
                        request
                    )
                )

                self._write(
                    handle,
                    response,
                )

            finally:

                try:

                    kernel32.DisconnectNamedPipe(
                        handle
                    )

                except Exception:

                    pass

                kernel32.CloseHandle(
                    handle
                )

            if (
                stop_event is not None
                and stop_event.is_set()
            ):

                return