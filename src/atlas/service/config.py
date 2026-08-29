from __future__ import annotations

import json
import os
import re

from pathlib import Path
from typing import Any


SERVICE_NAME = "SIDERONService"

SERVICE_DISPLAY_NAME = (
    "Sideron V2 Privileged Service"
)

SERVICE_DESCRIPTION = (
    "Service privilégié local d'Sideron V2."
)


PROGRAM_DATA = Path(
    os.environ.get(
        "ProgramData",
        r"C:\ProgramData",
    )
)

SIDERON_SERVICE_DATA_DIRECTORY = (
    PROGRAM_DATA
    / "SIDERON"
)

SERVICE_CONFIG_PATH = (
    SIDERON_SERVICE_DATA_DIRECTORY
    / "service_config.json"
)

SERVICE_LOG_PATH = (
    SIDERON_SERVICE_DATA_DIRECTORY
    / "sideron_service.log"
)


SID_PATTERN = re.compile(
    r"^S-\d+(?:-\d+)+$"
)


class SideronServiceConfigError(
    RuntimeError
):
    pass


def validate_sid(
    sid: str,
) -> str:

    if not isinstance(
        sid,
        str,
    ):

        raise SideronServiceConfigError(
            "Le SID doit être une chaîne."
        )

    sid = sid.strip()

    if not SID_PATTERN.fullmatch(
        sid
    ):

        raise SideronServiceConfigError(
            "Le SID utilisateur Sideron "
            "est invalide."
        )

    return sid


def ensure_data_directory(
) -> Path:

    SIDERON_SERVICE_DATA_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    return (
        SIDERON_SERVICE_DATA_DIRECTORY
    )


def save_service_config(
    allowed_user_sid: str,
) -> Path:

    allowed_user_sid = (
        validate_sid(
            allowed_user_sid
        )
    )

    ensure_data_directory()

    payload = {
        "version": 1,
        "allowed_user_sid": (
            allowed_user_sid
        ),
    }

    temporary_path = (
        SERVICE_CONFIG_PATH
        .with_suffix(
            ".tmp"
        )
    )

    temporary_path.write_text(
        json.dumps(
            payload,
            indent=4,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(
        SERVICE_CONFIG_PATH
    )

    return SERVICE_CONFIG_PATH


def load_service_config(
) -> dict[str, Any]:

    if not SERVICE_CONFIG_PATH.exists():

        raise SideronServiceConfigError(
            "Configuration SideronService "
            f"introuvable : {SERVICE_CONFIG_PATH}"
        )

    try:

        payload = json.loads(
            SERVICE_CONFIG_PATH.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:

        raise SideronServiceConfigError(
            "Impossible de lire la "
            "configuration SideronService."
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):

        raise SideronServiceConfigError(
            "Format de configuration "
            "SideronService invalide."
        )

    version = payload.get(
        "version"
    )

    if version != 1:

        raise SideronServiceConfigError(
            "Version de configuration "
            "SideronService incompatible."
        )

    allowed_user_sid = (
        validate_sid(
            payload.get(
                "allowed_user_sid",
                "",
            )
        )
    )

    return {
        "version": 1,
        "allowed_user_sid": (
            allowed_user_sid
        ),
    }


def get_allowed_user_sid(
) -> str:

    config = (
        load_service_config()
    )

    return config[
        "allowed_user_sid"
    ]
