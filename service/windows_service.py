from __future__ import annotations

import ctypes
import sys
import threading
import traceback

from ctypes import wintypes
from pathlib import Path


# =========================================================
# Bootstrap
# =========================================================

ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

SRC = (
    ROOT
    / "src"
)

sys.path.insert(
    0,
    str(SRC),
)

SERVICE_DIRECTORY = (
    ROOT
    / "service"
)

sys.path.insert(
    0,
    str(SERVICE_DIRECTORY),
)


from atlas.service.config import (
    SERVICE_LOG_PATH,
    SERVICE_NAME,
    ensure_data_directory,
    get_allowed_user_sid,
)

from atlas.service.pipe_client import (
    WindowsNamedPipeClient,
)

from atlas.service.protocol import (
    PROTOCOL_VERSION,
    ServiceRequest,
)

from atlas_service import (
    AtlasServiceServer,
)

from pipe_server import (
    AtlasPipeServer,
)


# =========================================================
# Constantes Windows Service
# =========================================================

SERVICE_WIN32_OWN_PROCESS = 0x00000010

SERVICE_STOPPED = 0x00000001
SERVICE_START_PENDING = 0x00000002
SERVICE_STOP_PENDING = 0x00000003
SERVICE_RUNNING = 0x00000004

SERVICE_ACCEPT_STOP = 0x00000001
SERVICE_ACCEPT_SHUTDOWN = 0x00000004

SERVICE_CONTROL_STOP = 0x00000001
SERVICE_CONTROL_SHUTDOWN = 0x00000005

NO_ERROR = 0


# =========================================================
# Structures
# =========================================================


class SERVICE_STATUS(
    ctypes.Structure
):

    _fields_ = [
        (
            "dwServiceType",
            wintypes.DWORD,
        ),
        (
            "dwCurrentState",
            wintypes.DWORD,
        ),
        (
            "dwControlsAccepted",
            wintypes.DWORD,
        ),
        (
            "dwWin32ExitCode",
            wintypes.DWORD,
        ),
        (
            "dwServiceSpecificExitCode",
            wintypes.DWORD,
        ),
        (
            "dwCheckPoint",
            wintypes.DWORD,
        ),
        (
            "dwWaitHint",
            wintypes.DWORD,
        ),
    ]


SERVICE_MAIN_FUNCTION = (
    ctypes.WINFUNCTYPE(
        None,
        wintypes.DWORD,
        ctypes.POINTER(
            wintypes.LPWSTR
        ),
    )
)


SERVICE_HANDLER_FUNCTION_EX = (
    ctypes.WINFUNCTYPE(
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
    )
)


class SERVICE_TABLE_ENTRY(
    ctypes.Structure
):

    _fields_ = [
        (
            "lpServiceName",
            wintypes.LPWSTR,
        ),
        (
            "lpServiceProc",
            SERVICE_MAIN_FUNCTION,
        ),
    ]


# =========================================================
# DLL
# =========================================================

advapi32 = ctypes.WinDLL(
    "advapi32",
    use_last_error=True,
)


advapi32.StartServiceCtrlDispatcherW.argtypes = [
    ctypes.POINTER(
        SERVICE_TABLE_ENTRY
    ),
]

advapi32.StartServiceCtrlDispatcherW.restype = (
    wintypes.BOOL
)


advapi32.RegisterServiceCtrlHandlerExW.argtypes = [
    wintypes.LPCWSTR,
    SERVICE_HANDLER_FUNCTION_EX,
    wintypes.LPVOID,
]

advapi32.RegisterServiceCtrlHandlerExW.restype = (
    wintypes.HANDLE
)


advapi32.SetServiceStatus.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(
        SERVICE_STATUS
    ),
]

advapi32.SetServiceStatus.restype = (
    wintypes.BOOL
)


# =========================================================
# Runtime
# =========================================================


class AtlasWindowsService:

    def __init__(
        self,
    ) -> None:

        self.status_handle = None

        self.stop_event = (
            threading.Event()
        )

        self.server_thread: (
            threading.Thread | None
        ) = None

        self.status = (
            SERVICE_STATUS()
        )

        self.status.dwServiceType = (
            SERVICE_WIN32_OWN_PROCESS
        )

        self.checkpoint = 0

    # =====================================================
    # Logs
    # =====================================================

    def _initialize_logging(
        self,
    ) -> None:

        ensure_data_directory()

        log_file = open(
            SERVICE_LOG_PATH,
            "a",
            encoding="utf-8",
            buffering=1,
        )

        sys.stdout = log_file
        sys.stderr = log_file

        print()
        print(
            "========================================"
        )
        print(
            " AtlasService Windows"
        )
        print(
            "========================================"
        )

    # =====================================================
    # Status
    # =====================================================

    def set_status(
        self,
        state: int,
        controls_accepted: int = 0,
        wait_hint: int = 0,
        win32_exit_code: int = 0,
    ) -> None:

        if self.status_handle is None:

            return

        if state in {
            SERVICE_START_PENDING,
            SERVICE_STOP_PENDING,
        }:

            self.checkpoint += 1

        else:

            self.checkpoint = 0

        self.status.dwCurrentState = (
            state
        )

        self.status.dwControlsAccepted = (
            controls_accepted
        )

        self.status.dwWin32ExitCode = (
            win32_exit_code
        )

        self.status.dwServiceSpecificExitCode = (
            0
        )

        self.status.dwCheckPoint = (
            self.checkpoint
        )

        self.status.dwWaitHint = (
            wait_hint
        )

        advapi32.SetServiceStatus(
            self.status_handle,
            ctypes.byref(
                self.status
            ),
        )

    # =====================================================
    # Stop
    # =====================================================

    def request_stop(
        self,
    ) -> None:

        if self.stop_event.is_set():

            return

        self.set_status(
            SERVICE_STOP_PENDING,
            controls_accepted=0,
            wait_hint=35000,
        )

        self.stop_event.set()

        # Le serveur peut être bloqué dans
        # ConnectNamedPipe.
        #
        # Un ping local le réveille afin qu'il
        # puisse constater stop_event.

        try:

            client = (
                WindowsNamedPipeClient(
                    timeout_seconds=2.0
                )
            )

            request = (
                ServiceRequest(
                    action="ping",
                    parameters={},
                )
                .to_bytes()
            )

            client.exchange(
                request
            )

        except Exception:

            pass

    # =====================================================
    # Control Handler
    # =====================================================

    def control_handler(
        self,
        control: int,
        event_type: int,
        event_data,
        context,
    ) -> int:

        if control in {
            SERVICE_CONTROL_STOP,
            SERVICE_CONTROL_SHUTDOWN,
        }:

            self.request_stop()

            return NO_ERROR

        return NO_ERROR

    # =====================================================
    # Service main
    # =====================================================

    def run_service(
        self,
    ) -> None:

        self._initialize_logging()

        print(
            "Initialisation AtlasService..."
        )

        allowed_user_sid = (
            get_allowed_user_sid()
        )

        print(
            "SID Atlas autorisé :",
            allowed_user_sid,
        )

        service_server = (
            AtlasServiceServer()
        )

        pipe_server = (
            AtlasPipeServer(
                allowed_user_sid=(
                    allowed_user_sid
                )
            )
        )

        self.server_thread = (
            threading.Thread(
                target=(
                    pipe_server
                    .serve_forever
                ),
                kwargs={
                    "request_handler": (
                        service_server
                        ._handle_raw_request
                    ),
                    "stop_event": (
                        self.stop_event
                    ),
                },
                name=(
                    "AtlasServicePipe"
                ),
                daemon=True,
            )
        )

        self.server_thread.start()

        self.set_status(
            SERVICE_RUNNING,
            controls_accepted=(
                SERVICE_ACCEPT_STOP
                | SERVICE_ACCEPT_SHUTDOWN
            ),
        )

        print(
            "AtlasService démarré."
        )

        self.stop_event.wait()

        print(
            "Arrêt AtlasService..."
        )

        if (
            self.server_thread
            is not None
        ):

            self.server_thread.join(
                timeout=35.0
            )

        self.set_status(
            SERVICE_STOPPED,
        )

        print(
            "AtlasService arrêté."
        )


# =========================================================
# Global
# =========================================================

SERVICE_RUNTIME = (
    AtlasWindowsService()
)


@SERVICE_HANDLER_FUNCTION_EX
def service_control_handler(
    control,
    event_type,
    event_data,
    context,
):

    return (
        SERVICE_RUNTIME.control_handler(
            control,
            event_type,
            event_data,
            context,
        )
    )


@SERVICE_MAIN_FUNCTION
def service_main(
    argc,
    argv,
):

    try:

        SERVICE_RUNTIME.status_handle = (
            advapi32
            .RegisterServiceCtrlHandlerExW(
                SERVICE_NAME,
                service_control_handler,
                None,
            )
        )

        if not (
            SERVICE_RUNTIME
            .status_handle
        ):

            return

        SERVICE_RUNTIME.set_status(
            SERVICE_START_PENDING,
            wait_hint=15000,
        )

        SERVICE_RUNTIME.run_service()

    except Exception:

        try:

            ensure_data_directory()

            with open(
                SERVICE_LOG_PATH,
                "a",
                encoding="utf-8",
            ) as log_file:

                log_file.write(
                    "\nERREUR FATALE ATLAS SERVICE\n"
                )

                traceback.print_exc(
                    file=log_file
                )

        except Exception:

            pass

        SERVICE_RUNTIME.set_status(
            SERVICE_STOPPED,
            win32_exit_code=1,
        )


# Références globales obligatoires pour empêcher
# le garbage collector de libérer les callbacks.
_SERVICE_MAIN_CALLBACK = (
    service_main
)

_SERVICE_CONTROL_CALLBACK = (
    service_control_handler
)


def run_self_test(
) -> int:

    # Ce test ne démarre pas le Named Pipe et ne requiert
    # pas encore de configuration dans C:\ProgramData\Atlas.
    # Il valide simplement que le bundle peut charger les
    # composants critiques du service autonome.

    if PROTOCOL_VERSION <= 0:

        return 10

    if not callable(
        AtlasServiceServer
    ):

        return 11

    if not callable(
        AtlasPipeServer
    ):

        return 12

    return 0


def main(
) -> int:

    if "--self-test" in sys.argv:

        return run_self_test()

    service_table = (
        SERVICE_TABLE_ENTRY
        * 2
    )()

    service_table[0].lpServiceName = (
        SERVICE_NAME
    )

    service_table[0].lpServiceProc = (
        _SERVICE_MAIN_CALLBACK
    )

    service_table[1].lpServiceName = (
        None
    )

    service_table[1].lpServiceProc = (
        SERVICE_MAIN_FUNCTION()
    )

    success = (
        advapi32
        .StartServiceCtrlDispatcherW(
            service_table
        )
    )

    if not success:

        error = (
            ctypes.get_last_error()
        )

        raise RuntimeError(
            "Impossible de connecter "
            "AtlasService au Service Control "
            f"Manager : {ctypes.WinError(error)}"
        )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )