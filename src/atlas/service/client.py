from __future__ import annotations

from typing import Any

from atlas.service.pipe_client import (
    PipeAccessDeniedError,
    PipeClientError,
    PipeUnavailableError,
    WindowsNamedPipeClient,
)

from atlas.service.protocol import (
    PROTOCOL_VERSION,
    ServiceProtocolError,
    ServiceRequest,
    ServiceResponse,
)


class AtlasServiceError(
    RuntimeError
):
    pass


class AtlasServiceUnavailableError(
    AtlasServiceError
):
    pass


class AtlasServiceProtocolError(
    AtlasServiceError
):
    pass


class AtlasServiceClient:

    def __init__(
        self,
        logger=None,
    ) -> None:

        self.logger = logger

        self.pipe = (
            WindowsNamedPipeClient(
                timeout_seconds=35.0
            )
        )

    # =====================================================
    # Requête générique
    # =====================================================

    def request(
        self,
        action: str,
        parameters: (
            dict[str, Any] | None
        ) = None,
    ) -> ServiceResponse:

        request = ServiceRequest(
            action=action,
            parameters=(
                parameters or {}
            ),
        )

        if self.logger is not None:

            self.logger.debug(
                "AtlasService request : %s %s",
                request.action,
                request.parameters,
            )

        try:

            response_payload = (
                self.pipe.exchange(
                    request.to_bytes()
                )
            )

        except PipeUnavailableError as exc:

            raise (
                AtlasServiceUnavailableError(
                    "AtlasService n'est pas "
                    "disponible."
                )
            ) from exc

        except PipeAccessDeniedError as exc:

            raise AtlasServiceError(
                "Atlas n'est pas autorisé "
                "à communiquer avec AtlasService."
            ) from exc

        except PipeClientError as exc:

            raise AtlasServiceError(
                str(
                    exc
                )
            ) from exc

        try:

            response = (
                ServiceResponse.from_bytes(
                    response_payload
                )
            )

        except ServiceProtocolError as exc:

            raise (
                AtlasServiceProtocolError(
                    str(
                        exc
                    )
                )
            ) from exc

        if (
            response.protocol_version
            != PROTOCOL_VERSION
        ):

            raise AtlasServiceProtocolError(
                "Version du protocole "
                "AtlasService incompatible."
            )

        if self.logger is not None:

            self.logger.debug(
                "AtlasService response : "
                "%s | %s",
                response.success,
                response.message,
            )

        return response

    # =====================================================
    # Ping
    # =====================================================

    def ping(
        self,
    ) -> ServiceResponse:

        return self.request(
            action="ping",
        )

    # =====================================================
    # Start service
    # =====================================================

    def start_service(
        self,
        service_name: str,
    ) -> ServiceResponse:

        return self.request(
            action="service.start",
            parameters={
                "name": service_name,
            },
        )

    # =====================================================
    # Stop service
    # =====================================================

    def stop_service(
        self,
        service_name: str,
    ) -> ServiceResponse:

        return self.request(
            action="service.stop",
            parameters={
                "name": service_name,
            },
        )

    # =====================================================
    # Restart service
    # =====================================================

    def restart_service(
        self,
        service_name: str,
    ) -> ServiceResponse:

        return self.request(
            action="service.restart",
            parameters={
                "name": service_name,
            },
        )

    # =====================================================
    # Restart computer
    # =====================================================

    def restart_computer(
        self,
    ) -> ServiceResponse:

        return self.request(
            action="system.restart",
        )

    # =====================================================
    # Shutdown computer
    # =====================================================

    def shutdown_computer(
        self,
    ) -> ServiceResponse:

        return self.request(
            action="system.shutdown",
        )

    # =====================================================
    # Cancel shutdown
    # =====================================================

    def cancel_shutdown(
        self,
    ) -> ServiceResponse:

        return self.request(
            action="system.cancel_shutdown",
        )

    # =====================================================
    # Kill process
    # =====================================================

    def kill_process(
        self,
        pid: int,
        expected_name: str,
    ) -> ServiceResponse:

        return self.request(
            action="process.kill",
            parameters={
                "pid": pid,
                "expected_name": expected_name,
            },
        )


    # =====================================================
    # Flush DNS
    # =====================================================

    def flush_dns(
        self,
    ) -> ServiceResponse:

        return self.request(
            action="network.flush_dns",
        )

    # =====================================================
    # Renew DHCP
    # =====================================================

    def renew_dhcp(
        self,
        adapter: str | None = None,
    ) -> ServiceResponse:

        parameters = {}

        if adapter is not None:
            parameters["adapter"] = adapter

        return self.request(
            action="network.renew_dhcp",
            parameters=parameters,
        )

