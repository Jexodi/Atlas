import json
import os
import sys
from pathlib import Path
from typing import Any


class ConfigManager:

    DEFAULT_CONFIG_PATH = Path(
        "config"
    ) / "sideron.json"

    ENV_CONFIG_PATH = "SIDERON_CONFIG_PATH"
    LEGACY_ENV_CONFIG_PATH = "ATLAS_CONFIG_PATH"

    def __init__(
        self,
        config_path: str = "config/sideron.json",
    ):
        self._requested_config_path = Path(
            config_path
        )

        self.config_path = (
            self._resolve_config_path(
                self._requested_config_path
            )
        )

        self._config: dict[
            str,
            Any,
        ] = {}

    def load(self) -> None:

        # Re-résout le chemin au chargement afin de supporter un
        # changement éventuel de répertoire de travail au démarrage.
        self.config_path = (
            self._resolve_config_path(
                self._requested_config_path
            )
        )

        if not self.config_path.exists():

            searched = "\n - ".join(
                str(path)
                for path in self._candidate_paths(
                    self._requested_config_path
                )
            )

            raise FileNotFoundError(
                "Configuration introuvable.\n"
                f"Chemin demandé : "
                f"{self._requested_config_path}\n"
                "Chemins recherchés :\n - "
                f"{searched}"
            )

        with self.config_path.open(
            "r",
            encoding="utf-8"
        ) as file:

            self._config = json.load(
                file
            )

    def get(
        self,
        key: str,
        default: Any = None
    ) -> Any:

        value: Any = self._config

        for part in key.split("."):

            if not isinstance(
                value,
                dict,
            ):
                return default

            if part not in value:
                return default

            value = value[
                part
            ]

        return value

    @property
    def data(
        self,
    ) -> dict[str, Any]:

        return self._config

    def set(
        self,
        key: str,
        value: Any,
    ) -> None:

        parts = key.split(".")

        current = self._config

        for part in parts[:-1]:

            if part not in current:
                current[part] = {}

            child = current[
                part
            ]

            if not isinstance(
                child,
                dict,
            ):
                raise ValueError(
                    f"La clé '{part}' "
                    "n'est pas un objet."
                )

            current = child

        current[
            parts[-1]
        ] = value

    @classmethod
    def _runtime_config_path(
        cls,
    ) -> Path:

        local_app_data = os.getenv(
            "LOCALAPPDATA"
        )

        if local_app_data:

            return (
                Path(
                    local_app_data
                )
                / "SIDERON"
                / "config"
                / "sideron.json"
            )

        return (
            Path.home()
            / "AppData"
            / "Local"
            / "SIDERON"
            / "config"
            / "sideron.json"
        )

    def save(self) -> None:

        env_path = os.getenv(
            self.ENV_CONFIG_PATH
        )

        if env_path:
            self.config_path = Path(
                env_path
            ).expanduser()
        elif not self._requested_config_path.is_absolute():
            self.config_path = (
                self._runtime_config_path()
            )

        self.config_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.config_path.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                self._config,
                file,
                ensure_ascii=False,
                indent=4,
            )

            file.write(
                "\n"
            )

    @classmethod
    def _resolve_config_path(
        cls,
        requested_path: Path,
    ) -> Path:

        for candidate in cls._candidate_paths(
            requested_path
        ):

            if candidate.exists():

                return candidate

        # Garde un chemin déterministe pour les messages d'erreur
        # et pour un éventuel save() avant création.
        candidates = cls._candidate_paths(
            requested_path
        )

        if candidates:
            return candidates[0]

        return requested_path

    @classmethod
    def _candidate_paths(
        cls,
        requested_path: Path,
    ) -> list[Path]:

        candidates: list[
            Path
        ] = []

        def add(
            path: Path | None,
        ) -> None:

            if path is None:
                return

            try:
                resolved = path.expanduser().resolve(
                    strict=False
                )
            except OSError:
                resolved = path.expanduser()

            if resolved not in candidates:
                candidates.append(
                    resolved
                )

        # 1. Chemin explicitement fourni par l'environnement.
        env_path = os.getenv(
            cls.ENV_CONFIG_PATH
        ) or os.getenv(cls.LEGACY_ENV_CONFIG_PATH)

        if env_path:
            add(
                Path(
                    env_path
                )
            )

        # Un chemin absolu demandé reste prioritaire.
        if requested_path.is_absolute():

            add(
                requested_path
            )

            return candidates

        # 2. Configuration runtime utilisateur.
        if requested_path == cls.DEFAULT_CONFIG_PATH:
            add(
                cls._runtime_config_path()
            )

        # 3. Répertoire de travail courant (développement / modèle installé).
        add(
            Path.cwd()
            / requested_path
        )

        # 4. Exécutable packagé PyInstaller.
        #
        # Distribution finale :
        #   Sideron\
        #     SIDERON.exe
        #     config\sideron.json
        #     core\SIDERON.Core.exe
        #
        # sys.executable pointe donc vers Sideron\core\SIDERON.Core.exe.
        if getattr(
            sys,
            "frozen",
            False,
        ):

            executable_dir = (
                Path(
                    sys.executable
                )
                .resolve(
                    strict=False
                )
                .parent
            )

            add(
                executable_dir
                / requested_path
            )

            add(
                executable_dir.parent
                / requested_path
            )

        # 5. Développement depuis les sources :
        # src/atlas/core/config.py -> racine Sideron à parents[3].
        try:

            source_root = (
                Path(
                    __file__
                )
                .resolve(
                    strict=False
                )
                .parents[3]
            )

            add(
                source_root
                / requested_path
            )

        except (
            IndexError,
            OSError,
        ):

            pass

        # 5. Racine d'installation standard de développement.
        add(
            Path(
                r"C:\SIDERON"
            )
            / requested_path
        )

        return candidates
