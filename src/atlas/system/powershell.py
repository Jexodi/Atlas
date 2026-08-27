from __future__ import annotations

import subprocess


_UTF8_OUTPUT_PREFIX = (
    "[Console]::OutputEncoding = "
    "[System.Text.UTF8Encoding]::new($false); "
)


def run_fixed_powershell(
    script: str,
    *,
    timeout: float,
    execution_policy: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """
    Exécute uniquement un script PowerShell prédéfini dans le code Atlas.

    Cette fonction n'est pas exposée à OpenAI et n'accepte aucune commande
    libre provenant d'un tool call.
    """

    if not isinstance(script, str) or not script.strip():
        raise ValueError(
            "Le script PowerShell fixe ne peut pas être vide."
        )

    if timeout <= 0:
        raise ValueError(
            "Le délai PowerShell doit être supérieur à zéro."
        )

    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
    ]

    if execution_policy is not None:
        command.extend(
            [
                "-ExecutionPolicy",
                execution_policy,
            ]
        )

    command.extend(
        [
            "-Command",
            _UTF8_OUTPUT_PREFIX + script,
        ]
    )

    creation_flags = 0
    startup_info = None

    if hasattr(
        subprocess,
        "CREATE_NO_WINDOW",
    ):
        creation_flags |= (
            subprocess.CREATE_NO_WINDOW
        )

    # Défense supplémentaire pour les environnements Windows
    # où CREATE_NO_WINDOW ne serait pas disponible/appliqué.
    if hasattr(
        subprocess,
        "STARTUPINFO",
    ):
        startup_info = (
            subprocess.STARTUPINFO()
        )

        startup_info.dwFlags |= (
            subprocess.STARTF_USESHOWWINDOW
        )

        startup_info.wShowWindow = (
            subprocess.SW_HIDE
        )

    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8-sig",
        errors="replace",
        timeout=timeout,
        shell=False,
        check=False,
        creationflags=creation_flags,
        startupinfo=startup_info,
    )
