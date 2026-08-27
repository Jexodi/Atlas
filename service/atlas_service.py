from __future__ import annotations

import os
import re
import subprocess
import sys
import time

from pathlib import Path
from typing import Any


# =========================================================
# Bootstrap src/
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


import psutil

from atlas.service.protocol import (
    PROTOCOL_VERSION,
    ServiceProtocolError,
    ServiceResponse,
    decode_message,
)

from pipe_server import (
    AtlasPipeServer,
)


SERVICE_NAME_PATTERN = re.compile(
    r"^[A-Za-z0-9_.-]{1,256}$"
)

SERVICE_OPERATION_TIMEOUT = 30.0

ERROR_NO_SHUTDOWN_IN_PROGRESS = 1116


PROTECTED_SERVICE_NAMES = {
    "atlasv2service",
}


PROTECTED_PROCESS_NAMES = {
    "system",
    "registry",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "services.exe",
    "lsass.exe",
    "winlogon.exe",
    "fontdrvhost.exe",
    "dwm.exe",
    "atlas.exe",
    "atlasv2.exe",
    "atlasservice.exe",
    "atlasv2service.exe",
}

PROCESS_TERMINATE_TIMEOUT = 5.0


class AtlasServiceServer:

    # =====================================================
    # Run
    # =====================================================

    def run(
        self,
    ) -> None:

        pipe_server = (
            AtlasPipeServer()
        )

        print()
        print(
            "========================================"
        )
        print(
            " AtlasService V2 - Mode développement"
        )
        print(
            "========================================"
        )
        print()

        print(
            f"PID : {os.getpid()}"
        )

        print(
            f"Protocol : {PROTOCOL_VERSION}"
        )

        print(
            "Utilisateur Atlas autorisé : "
            f"{pipe_server.allowed_user_sid}"
        )

        print()

        print(
            "Actions autorisées :"
        )

        print(
            " - ping"
        )

        print(
            " - service.start"
        )

        print(
            " - service.stop"
        )

        print(
            " - service.restart"
        )

        print(
            " - system.restart"
        )

        print(
            " - system.shutdown"
        )

        print(
            " - system.cancel_shutdown"
        )

        print(
            " - process.kill"
        )

        print(
            " - network.flush_dns"
        )

        print(
            " - network.renew_dhcp"
        )

        print()

        print(
            "AtlasService prêt."
        )

        print()

        try:

            pipe_server.serve_forever(
                self._handle_raw_request
            )

        except KeyboardInterrupt:

            print()
            print(
                "Arrêt demandé."
            )

        finally:

            print(
                "AtlasService arrêté."
            )

    # =====================================================
    # Requête brute
    # =====================================================

    def _handle_raw_request(
        self,
        raw_request: bytes,
    ) -> bytes:

        try:

            request = (
                decode_message(
                    raw_request
                )
            )

            response = (
                self.handle_request(
                    request
                )
            )

        except ServiceProtocolError as exc:

            response = (
                ServiceResponse(
                    success=False,
                    message=(
                        "Requête AtlasService invalide."
                    ),
                    error_code=(
                        "INVALID_REQUEST"
                    ),
                    data={
                        "error": str(
                            exc
                        ),
                    },
                )
            )

        except Exception as exc:

            response = (
                ServiceResponse(
                    success=False,
                    message=(
                        "Erreur interne AtlasService."
                    ),
                    error_code=(
                        "INTERNAL_ERROR"
                    ),
                    data={
                        "error": str(
                            exc
                        ),
                    },
                )
            )

        return response.to_bytes()

    # =====================================================
    # Validation requête
    # =====================================================

    def handle_request(
        self,
        request: Any,
    ) -> ServiceResponse:

        if not isinstance(
            request,
            dict,
        ):

            return ServiceResponse(
                success=False,
                message=(
                    "Format de requête invalide."
                ),
                error_code=(
                    "INVALID_REQUEST"
                ),
            )

        protocol_version = (
            request.get(
                "protocol_version"
            )
        )

        if (
            protocol_version
            != PROTOCOL_VERSION
        ):

            return ServiceResponse(
                success=False,
                message=(
                    "Version du protocole "
                    "incompatible."
                ),
                error_code=(
                    "PROTOCOL_MISMATCH"
                ),
            )

        action = request.get(
            "action"
        )

        parameters = request.get(
            "parameters"
        )

        if not isinstance(
            action,
            str,
        ):

            return ServiceResponse(
                success=False,
                message=(
                    "Action invalide."
                ),
                error_code=(
                    "INVALID_ACTION"
                ),
            )

        if not isinstance(
            parameters,
            dict,
        ):

            return ServiceResponse(
                success=False,
                message=(
                    "Paramètres invalides."
                ),
                error_code=(
                    "INVALID_PARAMETERS"
                ),
            )

        print(
            "Requête reçue :",
            action,
            parameters,
        )

        # =================================================
        # Allowlist
        # =================================================

        if action == "ping":

            return self._handle_ping()

        if action == "service.start":

            return self._handle_service_start(
                parameters
            )

        if action == "service.stop":

            return self._handle_service_stop(
                parameters
            )

        if action == "service.restart":

            return self._handle_service_restart(
                parameters
            )

        if action == "system.restart":

            return self._handle_system_restart(
                parameters
            )

        if action == "system.shutdown":

            return self._handle_system_shutdown(
                parameters
            )

        if action == "system.cancel_shutdown":

            return self._handle_system_cancel_shutdown(
                parameters
            )

        if action == "process.kill":

            return self._handle_process_kill(
                parameters
            )

        if action == "network.flush_dns":

            return self._handle_network_flush_dns(
                parameters
            )

        if action == "network.renew_dhcp":

            return self._handle_network_renew_dhcp(
                parameters
            )

        return ServiceResponse(
            success=False,
            message=(
                f"L'action '{action}' "
                "n'est pas autorisée."
            ),
            error_code=(
                "ACTION_NOT_ALLOWED"
            ),
        )

    # =====================================================
    # Ping
    # =====================================================

    def _handle_ping(
        self,
    ) -> ServiceResponse:

        return ServiceResponse(
            success=True,
            message=(
                "AtlasService répond correctement."
            ),
            data={
                "service": (
                    "AtlasService"
                ),
                "protocol_version": (
                    PROTOCOL_VERSION
                ),
                "pid": os.getpid(),
            },
        )

    # =====================================================
    # Validation paramètres système
    # =====================================================

    def _validate_empty_parameters(
        self,
        parameters: dict[str, Any],
    ) -> bool:

        return (
            isinstance(
                parameters,
                dict,
            )
            and not parameters
        )

    # =====================================================
    # Validation nom service
    # =====================================================

    def _validate_service_name(
        self,
        value: Any,
    ) -> str | None:

        if not isinstance(
            value,
            str,
        ):

            return None

        name = value.strip()

        if not (
            SERVICE_NAME_PATTERN
            .fullmatch(
                name
            )
        ):

            return None

        return name

    # =====================================================
    # Protection AtlasService
    # =====================================================

    def _is_protected_service(
        self,
        service_name: str,
    ) -> bool:

        return (
            service_name.casefold()
            in PROTECTED_SERVICE_NAMES
        )

    def _protected_service_response(
        self,
        service_name: str,
    ) -> ServiceResponse:

        return ServiceResponse(
            success=False,
            message=(
                f"Le service '{service_name}' "
                "est protégé et ne peut pas être "
                "contrôlé par AtlasService."
            ),
            error_code=(
                "PROTECTED_SERVICE"
            ),
        )

    # =====================================================
    # Status service
    # =====================================================

    def _get_service_status(
        self,
        service_name: str,
    ) -> str | None:

        try:

            service = (
                psutil.win_service_get(
                    service_name
                )
            )

            return (
                service.status()
            )

        except (
            psutil.NoSuchProcess,
            OSError,
        ):

            return None

    # =====================================================
    # Attente état service
    # =====================================================

    def _wait_for_status(
        self,
        service_name: str,
        expected_status: str,
        timeout: float = (
            SERVICE_OPERATION_TIMEOUT
        ),
    ) -> bool:

        deadline = (
            time.monotonic()
            + timeout
        )

        while (
            time.monotonic()
            < deadline
        ):

            status = (
                self._get_service_status(
                    service_name
                )
            )

            if status == expected_status:

                return True

            time.sleep(
                0.25
            )

        return False

    # =====================================================
    # SC.EXE
    # =====================================================

    def _run_sc(
        self,
        command: str,
        service_name: str,
    ) -> subprocess.CompletedProcess:

        return subprocess.run(
            [
                "sc.exe",
                command,
                service_name,
            ],
            capture_output=True,
            text=True,
            timeout=(
                SERVICE_OPERATION_TIMEOUT
            ),
            shell=False,
            check=False,
        )

    # =====================================================
    # Shutdown.exe
    # =====================================================

    def _run_shutdown(
        self,
        restart: bool,
    ) -> subprocess.CompletedProcess:

        operation = (
            "/r"
            if restart
            else "/s"
        )

        return subprocess.run(
            [
                "shutdown.exe",
                operation,
                "/t",
                "10",
            ],
            capture_output=True,
            text=True,
            timeout=10.0,
            shell=False,
            check=False,
        )

    def _run_cancel_shutdown(
        self,
    ) -> subprocess.CompletedProcess:

        return subprocess.run(
            [
                "shutdown.exe",
                "/a",
            ],
            capture_output=True,
            text=True,
            timeout=10.0,
            shell=False,
            check=False,
        )

    # =====================================================
    # System restart
    # =====================================================

    def _handle_system_restart(
        self,
        parameters: dict[str, Any],
    ) -> ServiceResponse:

        if not self._validate_empty_parameters(
            parameters
        ):

            return ServiceResponse(
                success=False,
                message=(
                    "Paramètres invalides pour "
                    "le redémarrage du système."
                ),
                error_code=(
                    "INVALID_PARAMETERS"
                ),
            )

        try:

            result = (
                self._run_shutdown(
                    restart=True
                )
            )

        except subprocess.TimeoutExpired:

            return ServiceResponse(
                success=False,
                message=(
                    "Impossible de programmer "
                    "le redémarrage de Windows."
                ),
                error_code=(
                    "SYSTEM_RESTART_TIMEOUT"
                ),
            )

        if result.returncode != 0:

            return ServiceResponse(
                success=False,
                message=(
                    "Windows a refusé le "
                    "redémarrage de l'ordinateur."
                ),
                error_code=(
                    "SYSTEM_RESTART_FAILED"
                ),
                data={
                    "returncode": (
                        result.returncode
                    ),
                    "stdout": (
                        result.stdout
                    ),
                    "stderr": (
                        result.stderr
                    ),
                },
            )

        return ServiceResponse(
            success=True,
            message=(
                "Le redémarrage de Windows "
                "est programmé dans 10 secondes."
            ),
            data={
                "operation": (
                    "restart"
                ),
                "delay_seconds": 10,
            },
        )

    # =====================================================
    # System shutdown
    # =====================================================

    def _handle_system_shutdown(
        self,
        parameters: dict[str, Any],
    ) -> ServiceResponse:

        if not self._validate_empty_parameters(
            parameters
        ):

            return ServiceResponse(
                success=False,
                message=(
                    "Paramètres invalides pour "
                    "l'arrêt du système."
                ),
                error_code=(
                    "INVALID_PARAMETERS"
                ),
            )

        try:

            result = (
                self._run_shutdown(
                    restart=False
                )
            )

        except subprocess.TimeoutExpired:

            return ServiceResponse(
                success=False,
                message=(
                    "Impossible de programmer "
                    "l'arrêt de Windows."
                ),
                error_code=(
                    "SYSTEM_SHUTDOWN_TIMEOUT"
                ),
            )

        if result.returncode != 0:

            return ServiceResponse(
                success=False,
                message=(
                    "Windows a refusé l'arrêt "
                    "de l'ordinateur."
                ),
                error_code=(
                    "SYSTEM_SHUTDOWN_FAILED"
                ),
                data={
                    "returncode": (
                        result.returncode
                    ),
                    "stdout": (
                        result.stdout
                    ),
                    "stderr": (
                        result.stderr
                    ),
                },
            )

        return ServiceResponse(
            success=True,
            message=(
                "L'arrêt de Windows est "
                "programmé dans 10 secondes."
            ),
            data={
                "operation": (
                    "shutdown"
                ),
                "delay_seconds": 10,
            },
        )

    # =====================================================
    # Cancel shutdown
    # =====================================================

    def _handle_system_cancel_shutdown(
        self,
        parameters: dict[str, Any],
    ) -> ServiceResponse:

        if not self._validate_empty_parameters(
            parameters
        ):

            return ServiceResponse(
                success=False,
                message=(
                    "Paramètres invalides pour "
                    "l'annulation de l'arrêt."
                ),
                error_code=(
                    "INVALID_PARAMETERS"
                ),
            )

        try:

            result = (
                self._run_cancel_shutdown()
            )

        except subprocess.TimeoutExpired:

            return ServiceResponse(
                success=False,
                message=(
                    "Le délai d'annulation "
                    "de l'arrêt a été dépassé."
                ),
                error_code=(
                    "SYSTEM_CANCEL_SHUTDOWN_TIMEOUT"
                ),
            )

        if (
            result.returncode
            == ERROR_NO_SHUTDOWN_IN_PROGRESS
        ):

            return ServiceResponse(
                success=True,
                message=(
                    "Aucun arrêt ou redémarrage "
                    "n'est actuellement programmé."
                ),
                data={
                    "cancelled": False,
                },
            )

        if result.returncode != 0:

            return ServiceResponse(
                success=False,
                message=(
                    "Windows a refusé l'annulation "
                    "de l'arrêt ou du redémarrage."
                ),
                error_code=(
                    "SYSTEM_CANCEL_SHUTDOWN_FAILED"
                ),
                data={
                    "returncode": (
                        result.returncode
                    ),
                    "stdout": (
                        result.stdout
                    ),
                    "stderr": (
                        result.stderr
                    ),
                },
            )

        return ServiceResponse(
            success=True,
            message=(
                "L'arrêt ou le redémarrage "
                "de Windows a été annulé."
            ),
            data={
                "cancelled": True,
            },
        )

    # =====================================================
    # Validation PID processus
    # =====================================================

    def _validate_process_pid(
        self,
        value: Any,
    ) -> int | None:

        if isinstance(
            value,
            bool,
        ):

            return None

        if not isinstance(
            value,
            int,
        ):

            return None

        if value <= 0:

            return None

        return value

    # =====================================================
    # Protection processus
    # =====================================================

    def _is_protected_process(
        self,
        pid: int,
        process_name: str,
    ) -> bool:

        if pid in {
            0,
            4,
            os.getpid(),
        }:

            return True

        return (
            process_name.casefold()
            in PROTECTED_PROCESS_NAMES
        )

    def _protected_process_response(
        self,
        pid: int,
        process_name: str,
    ) -> ServiceResponse:

        return ServiceResponse(
            success=False,
            message=(
                f"Le processus '{process_name}' "
                f"(PID {pid}) est protégé et ne peut "
                "pas être arrêté par AtlasService."
            ),
            error_code=(
                "PROTECTED_PROCESS"
            ),
            data={
                "pid": pid,
                "name": process_name,
            },
        )

    # =====================================================
    # Kill process
    # =====================================================

    # =====================================================
    # Flush DNS
    # =====================================================

    def _handle_network_flush_dns(
        self,
        parameters: dict[str, Any],
    ) -> ServiceResponse:

        if not self._validate_empty_parameters(
            parameters
        ):

            return ServiceResponse(
                success=False,
                message=(
                    "Paramètres invalides pour "
                    "le vidage du cache DNS."
                ),
                error_code=(
                    "INVALID_PARAMETERS"
                ),
            )

        try:

            result = subprocess.run(
                [
                    "ipconfig.exe",
                    "/flushdns",
                ],
                capture_output=True,
                text=True,
                timeout=15.0,
                shell=False,
                check=False,
            )

        except subprocess.TimeoutExpired:

            return ServiceResponse(
                success=False,
                message=(
                    "Le délai de vidage du cache DNS "
                    "a été dépassé."
                ),
                error_code=(
                    "NETWORK_FLUSH_DNS_TIMEOUT"
                ),
            )

        if result.returncode != 0:

            return ServiceResponse(
                success=False,
                message=(
                    "Windows a refusé le vidage "
                    "du cache DNS."
                ),
                error_code=(
                    "NETWORK_FLUSH_DNS_FAILED"
                ),
                data={
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
            )

        return ServiceResponse(
            success=True,
            message=(
                "Le cache DNS de Windows "
                "a été vidé."
            ),
            data={
                "flushed": True,
            },
        )

    # =====================================================
    # Renew DHCP
    # =====================================================

    def _handle_network_renew_dhcp(
        self,
        parameters: dict[str, Any],
    ) -> ServiceResponse:

        if not isinstance(
            parameters,
            dict,
        ):

            return ServiceResponse(
                success=False,
                message=(
                    "Paramètres invalides pour "
                    "le renouvellement DHCP."
                ),
                error_code=(
                    "INVALID_PARAMETERS"
                ),
            )

        unexpected_parameters = (
            set(parameters)
            - {"adapter"}
        )

        if unexpected_parameters:

            return ServiceResponse(
                success=False,
                message=(
                    "Paramètres invalides pour "
                    "le renouvellement DHCP."
                ),
                error_code=(
                    "INVALID_PARAMETERS"
                ),
            )

        adapter = parameters.get(
            "adapter"
        )

        if adapter is not None:

            if not isinstance(
                adapter,
                str,
            ):

                return ServiceResponse(
                    success=False,
                    message=(
                        "Nom d'interface réseau invalide."
                    ),
                    error_code=(
                        "INVALID_NETWORK_ADAPTER"
                    ),
                )

            adapter = adapter.strip()

            if not adapter:
                adapter = None

        if adapter is not None:

            known_adapters = {
                name.casefold(): name
                for name in psutil.net_if_addrs()
            }

            resolved_adapter = (
                known_adapters.get(
                    adapter.casefold()
                )
            )

            if resolved_adapter is None:

                return ServiceResponse(
                    success=False,
                    message=(
                        f"L'interface réseau '{adapter}' "
                        "est introuvable."
                    ),
                    error_code=(
                        "NETWORK_ADAPTER_NOT_FOUND"
                    ),
                )

            adapter = resolved_adapter

        command = [
            "ipconfig.exe",
            "/renew",
        ]

        if adapter is not None:
            command.append(adapter)

        try:

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30.0,
                shell=False,
                check=False,
            )

        except subprocess.TimeoutExpired:

            return ServiceResponse(
                success=False,
                message=(
                    "Le renouvellement DHCP a dépassé "
                    "le délai prévu."
                ),
                error_code=(
                    "NETWORK_RENEW_DHCP_TIMEOUT"
                ),
            )

        if result.returncode != 0:

            return ServiceResponse(
                success=False,
                message=(
                    "Windows n'a pas pu renouveler "
                    "le bail DHCP."
                ),
                error_code=(
                    "NETWORK_RENEW_DHCP_FAILED"
                ),
                data={
                    "adapter": adapter,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
            )

        if adapter is None:

            message = (
                "Les baux DHCP des interfaces réseau "
                "Windows ont été renouvelés."
            )

        else:

            message = (
                f"Le bail DHCP de l'interface '{adapter}' "
                "a été renouvelé."
            )

        return ServiceResponse(
            success=True,
            message=message,
            data={
                "renewed": True,
                "adapter": adapter,
            },
        )

    def _handle_process_kill(
        self,
        parameters: dict[str, Any],
    ) -> ServiceResponse:

        allowed_keys = {
            "pid",
            "expected_name",
        }

        if any(
            key not in allowed_keys
            for key in parameters
        ):

            return ServiceResponse(
                success=False,
                message=(
                    "Paramètres invalides pour "
                    "l'arrêt du processus."
                ),
                error_code=(
                    "INVALID_PARAMETERS"
                ),
            )

        pid = self._validate_process_pid(
            parameters.get(
                "pid"
            )
        )

        if pid is None:

            return ServiceResponse(
                success=False,
                message=(
                    "PID de processus invalide."
                ),
                error_code=(
                    "INVALID_PROCESS_PID"
                ),
            )

        expected_name = parameters.get(
            "expected_name"
        )

        if not isinstance(
            expected_name,
            str,
        ):

            return ServiceResponse(
                success=False,
                message=(
                    "Nom attendu du processus invalide."
                ),
                error_code=(
                    "INVALID_PROCESS_NAME"
                ),
            )

        expected_name = (
            expected_name.strip()
        )

        if not expected_name:

            return ServiceResponse(
                success=False,
                message=(
                    "Le nom attendu du processus "
                    "ne peut pas être vide."
                ),
                error_code=(
                    "INVALID_PROCESS_NAME"
                ),
            )

        try:

            process = psutil.Process(
                pid
            )

            process_name = (
                process.name()
                or ""
            )

        except psutil.NoSuchProcess:

            return ServiceResponse(
                success=False,
                message=(
                    f"Le processus PID {pid} "
                    "est introuvable."
                ),
                error_code=(
                    "PROCESS_NOT_FOUND"
                ),
                data={
                    "pid": pid,
                },
            )

        except psutil.AccessDenied:

            return ServiceResponse(
                success=False,
                message=(
                    f"Impossible de lire les informations "
                    f"du processus PID {pid}."
                ),
                error_code=(
                    "PROCESS_ACCESS_DENIED"
                ),
                data={
                    "pid": pid,
                },
            )

        if (
            process_name.casefold()
            != expected_name.casefold()
        ):

            return ServiceResponse(
                success=False,
                message=(
                    "Le processus ciblé a changé depuis "
                    "la demande initiale. Action annulée."
                ),
                error_code=(
                    "PROCESS_IDENTITY_MISMATCH"
                ),
                data={
                    "pid": pid,
                    "expected_name": expected_name,
                    "actual_name": process_name,
                },
            )

        if self._is_protected_process(
            pid,
            process_name,
        ):

            return (
                self._protected_process_response(
                    pid,
                    process_name,
                )
            )

        try:

            process.terminate()

            try:

                process.wait(
                    timeout=(
                        PROCESS_TERMINATE_TIMEOUT
                    )
                )

                forced = False

            except psutil.TimeoutExpired:

                process.kill()

                process.wait(
                    timeout=(
                        PROCESS_TERMINATE_TIMEOUT
                    )
                )

                forced = True

        except psutil.NoSuchProcess:

            return ServiceResponse(
                success=True,
                message=(
                    f"Le processus '{process_name}' "
                    f"(PID {pid}) était déjà arrêté."
                ),
                data={
                    "pid": pid,
                    "name": process_name,
                    "changed": False,
                    "forced": False,
                },
            )

        except psutil.AccessDenied:

            return ServiceResponse(
                success=False,
                message=(
                    f"Windows a refusé l'arrêt du "
                    f"processus '{process_name}' "
                    f"(PID {pid})."
                ),
                error_code=(
                    "PROCESS_ACCESS_DENIED"
                ),
                data={
                    "pid": pid,
                    "name": process_name,
                },
            )

        except psutil.TimeoutExpired:

            return ServiceResponse(
                success=False,
                message=(
                    f"Le processus '{process_name}' "
                    f"(PID {pid}) ne s'est pas arrêté "
                    "dans le délai prévu."
                ),
                error_code=(
                    "PROCESS_KILL_TIMEOUT"
                ),
                data={
                    "pid": pid,
                    "name": process_name,
                },
            )

        except OSError as exc:

            return ServiceResponse(
                success=False,
                message=(
                    f"Impossible d'arrêter le processus "
                    f"'{process_name}' (PID {pid})."
                ),
                error_code=(
                    "PROCESS_KILL_FAILED"
                ),
                data={
                    "pid": pid,
                    "name": process_name,
                    "error": str(
                        exc
                    ),
                },
            )

        return ServiceResponse(
            success=True,
            message=(
                f"Le processus '{process_name}' "
                f"(PID {pid}) a été arrêté."
            ),
            data={
                "pid": pid,
                "name": process_name,
                "changed": True,
                "forced": forced,
            },
        )

    # =====================================================
    # Start service
    # =====================================================

    def _handle_service_start(
        self,
        parameters: dict[str, Any],
    ) -> ServiceResponse:

        service_name = (
            self._validate_service_name(
                parameters.get(
                    "name"
                )
            )
        )

        if service_name is None:

            return ServiceResponse(
                success=False,
                message=(
                    "Nom de service invalide."
                ),
                error_code=(
                    "INVALID_SERVICE_NAME"
                ),
            )

        if self._is_protected_service(
            service_name
        ):

            return (
                self._protected_service_response(
                    service_name
                )
            )

        initial_status = (
            self._get_service_status(
                service_name
            )
        )

        if initial_status is None:

            return ServiceResponse(
                success=False,
                message=(
                    f"Le service '{service_name}' "
                    "est introuvable."
                ),
                error_code=(
                    "SERVICE_NOT_FOUND"
                ),
            )

        if initial_status == "running":

            return ServiceResponse(
                success=True,
                message=(
                    f"Le service '{service_name}' "
                    "est déjà démarré."
                ),
                data={
                    "name": service_name,
                    "initial_status": (
                        initial_status
                    ),
                    "final_status": (
                        "running"
                    ),
                    "changed": False,
                },
            )

        try:

            result = (
                self._run_sc(
                    "start",
                    service_name,
                )
            )

        except subprocess.TimeoutExpired:

            return ServiceResponse(
                success=False,
                message=(
                    "Le délai de démarrage du service "
                    f"'{service_name}' a été dépassé."
                ),
                error_code=(
                    "SERVICE_START_TIMEOUT"
                ),
            )

        if result.returncode != 0:

            return ServiceResponse(
                success=False,
                message=(
                    f"Impossible de démarrer "
                    f"le service '{service_name}'."
                ),
                error_code=(
                    "SERVICE_START_FAILED"
                ),
                data={
                    "returncode": (
                        result.returncode
                    ),
                    "stdout": (
                        result.stdout
                    ),
                    "stderr": (
                        result.stderr
                    ),
                },
            )

        if not self._wait_for_status(
            service_name,
            "running",
        ):

            return ServiceResponse(
                success=False,
                message=(
                    f"Le service '{service_name}' "
                    "ne s'est pas lancé dans "
                    "le délai prévu."
                ),
                error_code=(
                    "SERVICE_START_TIMEOUT"
                ),
            )

        return ServiceResponse(
            success=True,
            message=(
                f"Le service '{service_name}' "
                "a été démarré."
            ),
            data={
                "name": service_name,
                "initial_status": (
                    initial_status
                ),
                "final_status": (
                    "running"
                ),
                "changed": True,
            },
        )

    # =====================================================
    # Stop service
    # =====================================================

    def _handle_service_stop(
        self,
        parameters: dict[str, Any],
    ) -> ServiceResponse:

        service_name = (
            self._validate_service_name(
                parameters.get(
                    "name"
                )
            )
        )

        if service_name is None:

            return ServiceResponse(
                success=False,
                message=(
                    "Nom de service invalide."
                ),
                error_code=(
                    "INVALID_SERVICE_NAME"
                ),
            )

        if self._is_protected_service(
            service_name
        ):

            return (
                self._protected_service_response(
                    service_name
                )
            )

        initial_status = (
            self._get_service_status(
                service_name
            )
        )

        if initial_status is None:

            return ServiceResponse(
                success=False,
                message=(
                    f"Le service '{service_name}' "
                    "est introuvable."
                ),
                error_code=(
                    "SERVICE_NOT_FOUND"
                ),
            )

        if initial_status == "stopped":

            return ServiceResponse(
                success=True,
                message=(
                    f"Le service '{service_name}' "
                    "est déjà arrêté."
                ),
                data={
                    "name": service_name,
                    "initial_status": (
                        initial_status
                    ),
                    "final_status": (
                        "stopped"
                    ),
                    "changed": False,
                },
            )

        try:

            result = (
                self._run_sc(
                    "stop",
                    service_name,
                )
            )

        except subprocess.TimeoutExpired:

            return ServiceResponse(
                success=False,
                message=(
                    "Le délai d'arrêt du service "
                    f"'{service_name}' a été dépassé."
                ),
                error_code=(
                    "SERVICE_STOP_TIMEOUT"
                ),
            )

        if result.returncode != 0:

            return ServiceResponse(
                success=False,
                message=(
                    f"Impossible d'arrêter "
                    f"le service '{service_name}'."
                ),
                error_code=(
                    "SERVICE_STOP_FAILED"
                ),
                data={
                    "returncode": (
                        result.returncode
                    ),
                    "stdout": (
                        result.stdout
                    ),
                    "stderr": (
                        result.stderr
                    ),
                },
            )

        if not self._wait_for_status(
            service_name,
            "stopped",
        ):

            return ServiceResponse(
                success=False,
                message=(
                    f"Le service '{service_name}' "
                    "ne s'est pas arrêté dans "
                    "le délai prévu."
                ),
                error_code=(
                    "SERVICE_STOP_TIMEOUT"
                ),
            )

        return ServiceResponse(
            success=True,
            message=(
                f"Le service '{service_name}' "
                "a été arrêté."
            ),
            data={
                "name": service_name,
                "initial_status": (
                    initial_status
                ),
                "final_status": (
                    "stopped"
                ),
                "changed": True,
            },
        )

    # =====================================================
    # Restart service
    # =====================================================

    def _handle_service_restart(
        self,
        parameters: dict[str, Any],
    ) -> ServiceResponse:

        service_name = (
            self._validate_service_name(
                parameters.get(
                    "name"
                )
            )
        )

        if service_name is None:

            return ServiceResponse(
                success=False,
                message=(
                    "Nom de service invalide."
                ),
                error_code=(
                    "INVALID_SERVICE_NAME"
                ),
            )

        if self._is_protected_service(
            service_name
        ):

            return (
                self._protected_service_response(
                    service_name
                )
            )

        initial_status = (
            self._get_service_status(
                service_name
            )
        )

        if initial_status is None:

            return ServiceResponse(
                success=False,
                message=(
                    f"Le service '{service_name}' "
                    "est introuvable."
                ),
                error_code=(
                    "SERVICE_NOT_FOUND"
                ),
            )

        print(
            f"Restart service : "
            f"{service_name} "
            f"(état initial : {initial_status})"
        )

        if initial_status != "stopped":

            try:

                stop_result = (
                    self._run_sc(
                        "stop",
                        service_name,
                    )
                )

            except subprocess.TimeoutExpired:

                return ServiceResponse(
                    success=False,
                    message=(
                        "Le délai d'arrêt du service "
                        f"'{service_name}' a été dépassé."
                    ),
                    error_code=(
                        "SERVICE_STOP_TIMEOUT"
                    ),
                )

            if stop_result.returncode != 0:

                return ServiceResponse(
                    success=False,
                    message=(
                        "Impossible d'arrêter le service "
                        f"'{service_name}'."
                    ),
                    error_code=(
                        "SERVICE_STOP_FAILED"
                    ),
                    data={
                        "returncode": (
                            stop_result.returncode
                        ),
                        "stdout": (
                            stop_result.stdout
                        ),
                        "stderr": (
                            stop_result.stderr
                        ),
                    },
                )

            if not self._wait_for_status(
                service_name,
                "stopped",
            ):

                return ServiceResponse(
                    success=False,
                    message=(
                        f"Le service '{service_name}' "
                        "ne s'est pas arrêté dans "
                        "le délai prévu."
                    ),
                    error_code=(
                        "SERVICE_STOP_TIMEOUT"
                    ),
                )

        try:

            start_result = (
                self._run_sc(
                    "start",
                    service_name,
                )
            )

        except subprocess.TimeoutExpired:

            return ServiceResponse(
                success=False,
                message=(
                    "Le délai de démarrage du service "
                    f"'{service_name}' a été dépassé."
                ),
                error_code=(
                    "SERVICE_START_TIMEOUT"
                ),
            )

        if start_result.returncode != 0:

            return ServiceResponse(
                success=False,
                message=(
                    "Impossible de démarrer le service "
                    f"'{service_name}'."
                ),
                error_code=(
                    "SERVICE_START_FAILED"
                ),
                data={
                    "returncode": (
                        start_result.returncode
                    ),
                    "stdout": (
                        start_result.stdout
                    ),
                    "stderr": (
                        start_result.stderr
                    ),
                },
            )

        if not self._wait_for_status(
            service_name,
            "running",
        ):

            return ServiceResponse(
                success=False,
                message=(
                    f"Le service '{service_name}' "
                    "ne s'est pas lancé dans "
                    "le délai prévu."
                ),
                error_code=(
                    "SERVICE_START_TIMEOUT"
                ),
            )

        return ServiceResponse(
            success=True,
            message=(
                f"Le service '{service_name}' "
                "a été redémarré."
            ),
            data={
                "name": service_name,
                "initial_status": (
                    initial_status
                ),
                "final_status": (
                    "running"
                ),
                "changed": True,
            },
        )


def main() -> None:

    server = (
        AtlasServiceServer()
    )

    server.run()


if __name__ == "__main__":

    main()