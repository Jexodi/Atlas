from __future__ import annotations

import json

from dataclasses import dataclass
from typing import Any


PROTOCOL_VERSION = 2

PIPE_NAME = "AtlasV2Service"

PIPE_ADDRESS = (
    rf"\\.\pipe\{PIPE_NAME}"
)

MAX_MESSAGE_SIZE = 64 * 1024


class ServiceProtocolError(
    ValueError
):
    pass


@dataclass(slots=True)
class ServiceRequest:

    action: str

    parameters: dict[str, Any]

    protocol_version: int = (
        PROTOCOL_VERSION
    )

    def to_dict(
        self,
    ) -> dict[str, Any]:

        return {
            "protocol_version": (
                self.protocol_version
            ),
            "action": self.action,
            "parameters": (
                self.parameters
            ),
        }

    def to_bytes(
        self,
    ) -> bytes:

        return encode_message(
            self.to_dict()
        )


@dataclass(slots=True)
class ServiceResponse:

    success: bool

    message: str

    data: Any = None

    error_code: str | None = None

    protocol_version: int = (
        PROTOCOL_VERSION
    )

    def to_dict(
        self,
    ) -> dict[str, Any]:

        return {
            "protocol_version": (
                self.protocol_version
            ),
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "error_code": (
                self.error_code
            ),
        }

    def to_bytes(
        self,
    ) -> bytes:

        return encode_message(
            self.to_dict()
        )

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
    ) -> "ServiceResponse":

        return cls(
            protocol_version=payload.get(
                "protocol_version",
                0,
            ),
            success=bool(
                payload.get(
                    "success",
                    False,
                )
            ),
            message=str(
                payload.get(
                    "message",
                    "",
                )
            ),
            data=payload.get(
                "data"
            ),
            error_code=payload.get(
                "error_code"
            ),
        )

    @classmethod
    def from_bytes(
        cls,
        payload: bytes,
    ) -> "ServiceResponse":

        return cls.from_dict(
            decode_message(
                payload
            )
        )


def encode_message(
    payload: dict[str, Any],
) -> bytes:

    try:

        raw = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
        ).encode(
            "utf-8"
        )

    except (
        TypeError,
        ValueError,
    ) as exc:

        raise ServiceProtocolError(
            "Impossible de sérialiser "
            "le message AtlasService."
        ) from exc

    if len(raw) > MAX_MESSAGE_SIZE:

        raise ServiceProtocolError(
            "Le message AtlasService "
            "dépasse la taille maximale."
        )

    return raw


def decode_message(
    payload: bytes,
) -> dict[str, Any]:

    if not isinstance(
        payload,
        bytes,
    ):

        raise ServiceProtocolError(
            "Le message reçu n'est pas "
            "une séquence d'octets."
        )

    if len(payload) > MAX_MESSAGE_SIZE:

        raise ServiceProtocolError(
            "Le message reçu dépasse "
            "la taille maximale."
        )

    try:

        decoded = payload.decode(
            "utf-8"
        )

        data = json.loads(
            decoded
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:

        raise ServiceProtocolError(
            "Message JSON invalide."
        ) from exc

    if not isinstance(
        data,
        dict,
    ):

        raise ServiceProtocolError(
            "Le message JSON doit être "
            "un objet."
        )

    return data