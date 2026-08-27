from __future__ import annotations

import argparse
import ctypes
import subprocess
import sys

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
    ATLAS_SERVICE_DATA_DIRECTORY,
    SERVICE_CONFIG_PATH,
    SERVICE_DESCRIPTION,
    SERVICE_DISPLAY_NAME,
    SERVICE_NAME,
    save_service_config,
)

from atlas.service.pipe_security import (
    get_current_user_sid,
)


SYSTEM_SID = (
    "S-1-5-18"
)

ADMINISTRATORS_SID = (
    "S-1-5-32-544"
)


# =========================================================
# Admin
# =========================================================


def is_administrator(
) -> bool:

    try:

        return bool(
            ctypes.windll.shell32.IsUserAnAdmin()
        )

    except Exception:

        return False


# =========================================================
# Command
# =========================================================


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


# =========================================================
# Service existant
# =========================================================


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


# =========================================================
# ACL
# =========================================================


def secure_service_data(
    allowed_user_sid: str,
) -> None:

    directory = str(
        ATLAS_SERVICE_DATA_DIRECTORY
    )

    config = str(
        SERVICE_CONFIG_PATH
    )

    # Dossier :
    # SYSTEM / Administrateurs : Full Control
    # utilisateur Atlas : Read + Execute

    run_command(
        [
            "icacls.exe",
            directory,
            "/inheritance:r",
            "/grant:r",
            (
                f"*{SYSTEM_SID}:"
                "(OI)(CI)F"
            ),
            (
                f"*{ADMINISTRATORS_SID}:"
                "(OI)(CI)F"
            ),
            (
                f"*{allowed_user_sid}:"
                "(OI)(CI)RX"
            ),
        ]
    )

    # Configuration :
    # utilisateur Atlas peut la lire,
    # mais ne peut pas la modifier.

    run_command(
        [
            "icacls.exe",
            config,
            "/inheritance:r",
            "/grant:r",
            f"*{SYSTEM_SID}:F",
            f"*{ADMINISTRATORS_SID}:F",
            f"*{allowed_user_sid}:R",
        ]
    )


# =========================================================
# Executable AtlasService autonome
# =========================================================


def resolve_service_executable(
    explicit_path: str | None,
) -> Path:

    candidates: list[Path] = []

    if explicit_path:

        candidates.append(
            Path(explicit_path)
            .expanduser()
        )

    candidates.extend(
        [
            # Build de développement produit par
            # installer\\build_service.ps1.
            ROOT
            / "build"
            / "service-dist"
            / "Atlas.Service"
            / "Atlas.Service.exe",

            # Emplacements prévus pour la future release.
            ROOT
            / "Atlas.Service"
            / "Atlas.Service.exe",

            ROOT
            / "Atlas.Service.exe",
        ]
    )

    for candidate in candidates:

        candidate = (
            candidate
            .resolve()
        )

        if (
            candidate.exists()
            and candidate.is_file()
        ):

            return candidate

    searched = "\\n - ".join(
        str(candidate)
        for candidate in candidates
    )

    raise RuntimeError(
        "Atlas.Service.exe autonome introuvable. "
        "Lance d'abord installer\\build_service.ps1 "
        "ou indique --service-exe.\\n"
        f"Emplacements verifies :\\n - {searched}"
    )


def validate_service_executable(
    service_executable: Path,
) -> None:

    print(
        "Validation de l'executable autonome..."
    )

    result = run_command(
        [
            str(service_executable),
            "--self-test",
        ],
        check=False,
    )

    if result.returncode != 0:

        raise RuntimeError(
            "L'auto-test de Atlas.Service.exe "
            "a echoue "
            f"(code {result.returncode})."
        )

    print(
        "Atlas.Service.exe valide :",
        service_executable,
    )


# =========================================================
# Main
# =========================================================


def main(
) -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Installation du service "
            "privilégié Atlas V2."
        )
    )

    parser.add_argument(
        "--user-sid",
        default=None,
        help=(
            "SID explicitement autorisé à "
            f"communiquer avec {SERVICE_NAME}."
        ),
    )

    parser.add_argument(
        "--service-exe",
        default=None,
        help=(
            "Chemin explicite vers "
            "Atlas.Service.exe autonome."
        ),
    )

    args = parser.parse_args()

    print()
    print(
        "========================================"
    )
    print(
        f" Installation {SERVICE_NAME}"
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

    if service_exists():

        raise RuntimeError(
            f"Le service '{SERVICE_NAME}' "
            "existe déjà. Désinstalle-le "
            "avant de le réinstaller."
        )

    service_executable = (
        resolve_service_executable(
            args.service_exe
        )
    )

    validate_service_executable(
        service_executable
    )

    allowed_user_sid = (
        args.user_sid
        or get_current_user_sid()
    )

    print(
        "SID utilisateur Atlas :",
        allowed_user_sid,
    )

    print()

    # =====================================================
    # Configuration
    # =====================================================

    config_path = (
        save_service_config(
            allowed_user_sid
        )
    )

    print(
        "Configuration créée :",
        config_path,
    )

    secure_service_data(
        allowed_user_sid
    )

    # =====================================================
    # Service Windows
    # =====================================================

    binary_path = (
        f'"{service_executable}"'
    )

    run_command(
        [
            "sc.exe",
            "create",
            SERVICE_NAME,
            "binPath=",
            binary_path,
            "start=",
            "auto",
            "obj=",
            "LocalSystem",
            "DisplayName=",
            SERVICE_DISPLAY_NAME,
        ]
    )

    run_command(
        [
            "sc.exe",
            "description",
            SERVICE_NAME,
            SERVICE_DESCRIPTION,
        ]
    )

    # En cas de crash :
    # redémarrage du service après 5 secondes.

    run_command(
        [
            "sc.exe",
            "failure",
            SERVICE_NAME,
            "reset=",
            "86400",
            "actions=",
            "restart/5000",
        ]
    )

    print()
    print(
        "Service installé avec :",
        service_executable,
    )

    print()
    print(
        "Démarrage..."
    )

    run_command(
        [
            "sc.exe",
            "start",
            SERVICE_NAME,
        ]
    )

    print()
    print(
        "========================================"
    )
    print(
        f" {SERVICE_NAME} installé et démarré."
    )
    print(
        "========================================"
    )
    print()

    print(
        "Tu peux vérifier avec :"
    )

    print(
        f"sc.exe query {SERVICE_NAME}"
    )


if __name__ == "__main__":

    main()