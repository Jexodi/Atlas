from __future__ import annotations

import ctypes
import subprocess
import sys
import time

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


from atlas.service.config import (
    SERVICE_NAME,
)


def is_administrator(
) -> bool:

    try:

        return bool(
            ctypes.windll.shell32.IsUserAnAdmin()
        )

    except Exception:

        return False


def run_command(
    command: list[str],
    check: bool = True,
) -> subprocess.CompletedProcess:

    print(
        ">",
        subprocess.list2cmdline(
            command
        ),
    )

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )

    if result.stdout.strip():

        print(
            result.stdout.strip()
        )

    if result.stderr.strip():

        print(
            result.stderr.strip()
        )

    if (
        check
        and result.returncode != 0
    ):

        raise RuntimeError(
            "Commande échouée "
            f"(code {result.returncode})."
        )

    return result


def service_exists(
) -> bool:

    result = run_command(
        [
            "sc.exe",
            "query",
            SERVICE_NAME,
        ],
        check=False,
    )

    return (
        result.returncode == 0
    )


def main(
) -> None:

    print()
    print(
        "========================================"
    )
    print(
        f" Désinstallation {SERVICE_NAME}"
    )
    print(
        "========================================"
    )
    print()

    if not is_administrator():

        raise RuntimeError(
            "Ce programme doit être lancé "
            "depuis une console administrateur."
        )

    if not service_exists():

        print(
            f"{SERVICE_NAME} n'est pas installé."
        )

        return

    print(
        "Arrêt du service..."
    )

    run_command(
        [
            "sc.exe",
            "stop",
            SERVICE_NAME,
        ],
        check=False,
    )

    # Laisse le SCM quelques secondes
    # pour terminer proprement le processus.

    time.sleep(
        2.0
    )

    print(
        "Suppression du service..."
    )

    run_command(
        [
            "sc.exe",
            "delete",
            SERVICE_NAME,
        ]
    )

    print()
    print(
        f"{SERVICE_NAME} a été désinstallé."
    )

    print()
    print(
        "La configuration dans "
        "C:\\ProgramData\\Atlas est conservée."
    )


if __name__ == "__main__":

    main()