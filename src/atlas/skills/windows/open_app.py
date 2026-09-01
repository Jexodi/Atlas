from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from atlas.security.risk import RiskLevel
from atlas.skills.base import (
    Skill,
    SkillResult,
    SkillValidationError,
)


_SIMPLE_APP_RE = re.compile(r"^[A-Za-z0-9_.+-]+$")
_FORBIDDEN_SHELL_CHARS = frozenset("&|<>^;`\r\n")


class OpenAppSkill(Skill):

    name = "windows.open_app"

    description = (
        "Ouvre une application Windows à partir de son nom d'exécutable ou "
        "d'un chemin .exe. Cet outil n'accepte pas de commande shell ni "
        "d'arguments arbitraires."
    )

    parameters = {
        "type": "object",
        "properties": {
            "app": {
                "type": "string",
                "description": (
                    "Nom d'exécutable Windows, par exemple notepad ou chrome.exe, "
                    "ou chemin complet vers un fichier .exe."
                ),
            },
        },
        "required": [
            "app",
        ],
        "additionalProperties": False,
    }

    risk_level = RiskLevel.SAFE

    required_permission = None

    requires_service = False

    def validate(
        self,
        **kwargs,
    ) -> None:

        app = kwargs.get("app")

        if app is None:
            raise SkillValidationError(
                "Le paramètre 'app' est obligatoire."
            )

        if not isinstance(app, str):
            raise SkillValidationError(
                "Le paramètre 'app' doit être une chaîne."
            )

        value = app.strip()

        if not value:
            raise SkillValidationError(
                "Le nom de l'application ne peut pas être vide."
            )

        if any(char in value for char in _FORBIDDEN_SHELL_CHARS):
            raise SkillValidationError(
                "Les commandes shell et opérateurs de commande sont interdits."
            )

        if self._looks_like_path(value):
            path = Path(value).expanduser()
            if path.suffix.lower() != ".exe":
                raise SkillValidationError(
                    "Seuls les exécutables .exe peuvent être lancés par chemin."
                )
            if not path.is_file():
                raise SkillValidationError(
                    "Le fichier exécutable demandé est introuvable."
                )
            return

        if not _SIMPLE_APP_RE.fullmatch(value):
            raise SkillValidationError(
                "Indiquez uniquement un nom d'exécutable, sans argument de commande."
            )

    def execute(
        self,
        **kwargs,
    ) -> SkillResult:

        requested = kwargs["app"].strip()
        executable = self._resolve_executable(requested)

        if executable is None:
            return SkillResult(
                success=False,
                message=(
                    "Application introuvable. Indiquez son nom d'exécutable "
                    "ou son chemin .exe complet."
                ),
            )

        subprocess.Popen(
            [executable],
            shell=False,
        )

        return SkillResult(
            success=True,
            message=f"Application lancée : {requested}",
            data={
                "app": requested,
                "executable": executable,
            },
        )

    @staticmethod
    def _looks_like_path(value: str) -> bool:
        return (
            os.path.isabs(value)
            or "\\" in value
            or "/" in value
        )

    @classmethod
    def _resolve_executable(cls, value: str) -> str | None:
        if cls._looks_like_path(value):
            return str(Path(value).expanduser().resolve())

        candidates = [value]
        if not value.lower().endswith(".exe"):
            candidates.append(f"{value}.exe")

        for candidate in candidates:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved

        if os.name == "nt":
            resolved = cls._resolve_from_windows_app_paths(candidates)
            if resolved:
                return resolved

        return None

    @staticmethod
    def _resolve_from_windows_app_paths(candidates: list[str]) -> str | None:
        try:
            import winreg
        except ImportError:
            return None

        roots = (
            winreg.HKEY_CURRENT_USER,
            winreg.HKEY_LOCAL_MACHINE,
        )

        for candidate in candidates:
            exe_name = candidate if candidate.lower().endswith(".exe") else f"{candidate}.exe"
            subkey = rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"

            for root in roots:
                try:
                    with winreg.OpenKey(root, subkey) as key:
                        value, _ = winreg.QueryValueEx(key, None)
                except OSError:
                    continue

                if isinstance(value, str) and Path(value).is_file():
                    return value

        return None
