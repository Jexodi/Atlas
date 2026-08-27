from __future__ import annotations

import os
import shutil

from pathlib import Path

from atlas.storage.models import (
    ImportResult,
    StorageEntry,
)


class AtlasStorageError(Exception):
    """
    Erreur de base du système de stockage Atlas.
    """


class AtlasStoragePermissionError(
    AtlasStorageError
):
    """
    Une opération interdite a été demandée.
    """


class AtlasStorageNotFoundError(
    AtlasStorageError
):
    """
    Le fichier ou dossier demandé n'existe pas.
    """


class AtlasStorageUnsupportedFileError(
    AtlasStorageError
):
    """
    Le type de fichier demandé n'est pas autorisé
    pour la lecture texte.
    """


class AtlasStorage:

    TEXT_EXTENSIONS = {
        ".txt",
        ".md",
        ".markdown",
        ".log",
        ".csv",
        ".json",
        ".jsonl",
        ".xml",
        ".yaml",
        ".yml",
        ".ini",
        ".cfg",
        ".conf",
        ".toml",
        ".py",
        ".ps1",
        ".bat",
        ".cmd",
        ".html",
        ".htm",
        ".css",
        ".js",
        ".ts",
        ".sql",
    }

    def __init__(
        self,
        root: str | Path,
    ) -> None:

        self.root = self._normalize(
            root
        )

    # =====================================================
    # Initialisation
    # =====================================================

    def initialize(
        self,
    ) -> None:

        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

        directories = (
            "Documents",
            "Imports",
            "Exports",
            "Projects",
            "Memory",
            "Cache",
            "Temp",
            "Backups",
            "System",
        )

        for directory in directories:

            path = (
                self.root
                / directory
            )

            path.mkdir(
                parents=True,
                exist_ok=True,
            )

    # =====================================================
    # Normalisation
    # =====================================================

    def _normalize(
        self,
        path: str | Path,
    ) -> Path:

        return (
            Path(path)
            .expanduser()
            .resolve(
                strict=False
            )
        )

    # =====================================================
    # Vérification de confinement
    # =====================================================

    def is_inside_workspace(
        self,
        path: str | Path,
    ) -> bool:

        candidate = self._normalize(
            path
        )

        try:

            common = os.path.commonpath(
                [
                    os.path.normcase(
                        str(self.root)
                    ),
                    os.path.normcase(
                        str(candidate)
                    ),
                ]
            )

        except ValueError:

            return False

        return (
            os.path.normcase(
                common
            )
            == os.path.normcase(
                str(self.root)
            )
        )

    def require_workspace_path(
        self,
        path: str | Path,
    ) -> Path:

        candidate = self._normalize(
            path
        )

        if not self.is_inside_workspace(
            candidate
        ):

            raise AtlasStoragePermissionError(
                "Cette opération est interdite en dehors "
                "de la zone de stockage Atlas."
            )

        return candidate

    # =====================================================
    # Chemins relatifs au Workspace
    # =====================================================

    def workspace_path(
        self,
        relative_path: str | Path,
    ) -> Path:

        relative = Path(
            relative_path
        )

        if relative.is_absolute():

            raise AtlasStoragePermissionError(
                "Un chemin relatif à la zone Atlas "
                "est attendu."
            )

        candidate = self._normalize(
            self.root
            / relative
        )

        return self.require_workspace_path(
            candidate
        )

    # =====================================================
    # Vérification existence
    # =====================================================

    def _require_exists(
        self,
        path: str | Path,
    ) -> Path:

        candidate = self._normalize(
            path
        )

        if not candidate.exists():

            raise AtlasStorageNotFoundError(
                f"Chemin introuvable : {candidate}"
            )

        return candidate

    # =====================================================
    # Lecture texte
    # =====================================================

    def read_text(
        self,
        path: str | Path,
        *,
        max_bytes: int = 1_000_000,
    ) -> str:

        candidate = self._require_exists(
            path
        )

        if not candidate.is_file():

            raise AtlasStorageError(
                "Le chemin demandé n'est pas un fichier."
            )

        extension = (
            candidate.suffix.lower()
        )

        if (
            extension
            and extension
            not in self.TEXT_EXTENSIONS
        ):

            raise AtlasStorageUnsupportedFileError(
                f"Le fichier '{candidate.name}' "
                "n'est pas considéré comme un fichier texte."
            )

        size = (
            candidate.stat().st_size
        )

        if size > max_bytes:

            raise AtlasStorageError(
                "Le fichier est trop volumineux "
                f"pour être lu directement ({size} octets)."
            )

        return candidate.read_text(
            encoding="utf-8",
            errors="replace",
        )

    # =====================================================
    # Parcours dossier
    # =====================================================

    def list_directory(
        self,
        path: str | Path,
    ) -> list[StorageEntry]:

        candidate = self._require_exists(
            path
        )

        if not candidate.is_dir():

            raise AtlasStorageError(
                "Le chemin demandé n'est pas un dossier."
            )

        entries: list[StorageEntry] = []

        try:

            children = sorted(
                candidate.iterdir(),
                key=lambda item: (
                    not item.is_dir(),
                    item.name.lower(),
                ),
            )

        except PermissionError as exc:

            raise AtlasStoragePermissionError(
                f"Accès refusé : {candidate}"
            ) from exc

        for child in children:

            try:

                if child.is_dir():

                    entries.append(
                        StorageEntry(
                            name=child.name,
                            path=child,
                            entry_type="directory",
                        )
                    )

                elif child.is_file():

                    size = None

                    try:
                        size = child.stat().st_size
                    except OSError:
                        pass

                    entries.append(
                        StorageEntry(
                            name=child.name,
                            path=child,
                            entry_type="file",
                            size=size,
                        )
                    )

            except OSError:
                continue

        return entries

    # =====================================================
    # Recherche
    # =====================================================

    def search(
        self,
        root: str | Path,
        query: str,
        *,
        max_results: int = 100,
    ) -> list[StorageEntry]:

        search_root = self._require_exists(
            root
        )

        if not search_root.is_dir():

            raise AtlasStorageError(
                "La racine de recherche doit être un dossier."
            )

        query_normalized = (
            query.strip().casefold()
        )

        if not query_normalized:

            raise AtlasStorageError(
                "La recherche ne peut pas être vide."
            )

        results: list[StorageEntry] = []

        def on_error(
            error: OSError,
        ) -> None:

            return

        for (
            current_root,
            directories,
            files,
        ) in os.walk(
            search_root,
            topdown=True,
            onerror=on_error,
            followlinks=False,
        ):

            current_path = Path(
                current_root
            )

            for directory_name in directories:

                if (
                    query_normalized
                    in directory_name.casefold()
                ):

                    path = (
                        current_path
                        / directory_name
                    )

                    results.append(
                        StorageEntry(
                            name=directory_name,
                            path=path,
                            entry_type="directory",
                        )
                    )

                    if len(results) >= max_results:
                        return results

            for file_name in files:

                if (
                    query_normalized
                    in file_name.casefold()
                ):

                    path = (
                        current_path
                        / file_name
                    )

                    size = None

                    try:
                        size = path.stat().st_size
                    except OSError:
                        pass

                    results.append(
                        StorageEntry(
                            name=file_name,
                            path=path,
                            entry_type="file",
                            size=size,
                        )
                    )

                    if len(results) >= max_results:
                        return results

        return results

    # =====================================================
    # Import fichier
    # =====================================================

    def import_file(
        self,
        source: str | Path,
        destination_directory: str | Path = "Imports",
    ) -> ImportResult:

        source_path = self._require_exists(
            source
        )

        if not source_path.is_file():

            raise AtlasStorageError(
                "La source n'est pas un fichier."
            )

        destination_root = (
            self.workspace_path(
                destination_directory
            )
        )

        destination_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination = (
            destination_root
            / source_path.name
        )

        destination = (
            self._unique_destination(
                destination
            )
        )

        destination = (
            self.require_workspace_path(
                destination
            )
        )

        shutil.copy2(
            source_path,
            destination,
        )

        return ImportResult(
            source=source_path,
            destination=destination,
            copied=True,
        )

    # =====================================================
    # Import dossier
    # =====================================================

    def import_directory(
        self,
        source: str | Path,
        destination_directory: str | Path = "Imports",
    ) -> ImportResult:

        source_path = self._require_exists(
            source
        )

        if not source_path.is_dir():

            raise AtlasStorageError(
                "La source n'est pas un dossier."
            )

        destination_root = (
            self.workspace_path(
                destination_directory
            )
        )

        destination_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination = (
            destination_root
            / source_path.name
        )

        destination = (
            self._unique_destination(
                destination
            )
        )

        destination = (
            self.require_workspace_path(
                destination
            )
        )

        shutil.copytree(
            source_path,
            destination,
        )

        return ImportResult(
            source=source_path,
            destination=destination,
            copied=True,
        )

    # =====================================================
    # Gestion conflits de noms
    # =====================================================

    def _unique_destination(
        self,
        destination: Path,
    ) -> Path:

        destination = (
            self.require_workspace_path(
                destination
            )
        )

        if not destination.exists():
            return destination

        parent = destination.parent
        stem = destination.stem
        suffix = destination.suffix

        index = 1

        while True:

            candidate = (
                parent
                / f"{stem} ({index}){suffix}"
            )

            candidate = (
                self.require_workspace_path(
                    candidate
                )
            )

            if not candidate.exists():
                return candidate

            index += 1

    # =====================================================
    # Vérifications Workspace
    # =====================================================

    def workspace_exists(
        self,
        relative_path: str | Path,
    ) -> bool:

        return self.workspace_path(
            relative_path
        ).exists()

    def workspace_is_file(
        self,
        relative_path: str | Path,
    ) -> bool:

        return self.workspace_path(
            relative_path
        ).is_file()

    def workspace_is_directory(
        self,
        relative_path: str | Path,
    ) -> bool:

        return self.workspace_path(
            relative_path
        ).is_dir()

    # =====================================================
    # Création dossier
    # =====================================================

    def create_directory(
        self,
        relative_path: str | Path,
    ) -> Path:

        destination = self.workspace_path(
            relative_path
        )

        destination.mkdir(
            parents=True,
            exist_ok=True,
        )

        return destination

    # =====================================================
    # Création fichier texte
    # =====================================================

    def write_text(
        self,
        relative_path: str | Path,
        content: str,
        *,
        overwrite: bool = False,
    ) -> Path:

        destination = self.workspace_path(
            relative_path
        )

        extension = (
            destination.suffix.lower()
        )

        if (
            extension
            and extension
            not in self.TEXT_EXTENSIONS
        ):

            raise AtlasStorageUnsupportedFileError(
                f"Le fichier '{destination.name}' "
                "n'est pas considéré comme un fichier texte."
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if (
            destination.exists()
            and not overwrite
        ):

            raise AtlasStorageError(
                "Le fichier existe déjà et "
                "l'écrasement n'a pas été autorisé."
            )

        if (
            destination.exists()
            and destination.is_dir()
        ):

            raise AtlasStorageError(
                "Le chemin demandé correspond à un dossier."
            )

        destination.write_text(
            content,
            encoding="utf-8",
        )

        return destination

    # =====================================================
    # Modification fichier texte
    # =====================================================

    def write_existing_text(
        self,
        relative_path: str | Path,
        content: str,
    ) -> Path:

        destination = self.workspace_path(
            relative_path
        )

        if not destination.exists():

            raise AtlasStorageNotFoundError(
                f"Fichier introuvable : {destination}"
            )

        if not destination.is_file():

            raise AtlasStorageError(
                "Le chemin demandé n'est pas un fichier."
            )

        extension = (
            destination.suffix.lower()
        )

        if (
            extension
            and extension
            not in self.TEXT_EXTENSIONS
        ):

            raise AtlasStorageUnsupportedFileError(
                f"Le fichier '{destination.name}' "
                "n'est pas considéré comme un fichier texte."
            )

        destination.write_text(
            content,
            encoding="utf-8",
        )

        return destination

    # =====================================================
    # Renommage interne
    # =====================================================

    def rename(
        self,
        relative_path: str | Path,
        new_name: str,
    ) -> Path:

        source = self.workspace_path(
            relative_path
        )

        if not source.exists():

            raise AtlasStorageNotFoundError(
                f"Chemin introuvable : {source}"
            )

        if source == self.root:

            raise AtlasStoragePermissionError(
                "La racine Atlas ne peut pas être renommée."
            )

        new_name = new_name.strip()

        if not new_name:

            raise AtlasStorageError(
                "Le nouveau nom ne peut pas être vide."
            )

        if (
            Path(new_name).name
            != new_name
        ):

            raise AtlasStoragePermissionError(
                "Le nouveau nom ne doit pas contenir de chemin."
            )

        destination = (
            source.parent
            / new_name
        )

        destination = self.require_workspace_path(
            destination
        )

        if destination.exists():

            raise AtlasStorageError(
                "Un fichier ou dossier portant ce nom existe déjà."
            )

        source.rename(
            destination
        )

        return destination

    # =====================================================
    # Déplacement interne
    # =====================================================

    def move(
        self,
        source_relative_path: str | Path,
        destination_directory: str | Path,
    ) -> Path:

        source = self.workspace_path(
            source_relative_path
        )

        destination_root = self.workspace_path(
            destination_directory
        )

        if not source.exists():

            raise AtlasStorageNotFoundError(
                f"Chemin introuvable : {source}"
            )

        if source == self.root:

            raise AtlasStoragePermissionError(
                "La racine Atlas ne peut pas être déplacée."
            )

        if not destination_root.exists():

            raise AtlasStorageNotFoundError(
                f"Dossier de destination introuvable : "
                f"{destination_root}"
            )

        if not destination_root.is_dir():

            raise AtlasStorageError(
                "La destination doit être un dossier."
            )

        destination = (
            destination_root
            / source.name
        )

        destination = self.require_workspace_path(
            destination
        )

        if destination.exists():

            raise AtlasStorageError(
                "Un élément du même nom existe déjà "
                "dans le dossier de destination."
            )

        if (
            source.is_dir()
            and (
                destination_root == source
                or source in destination_root.parents
            )
        ):

            raise AtlasStorageError(
                "Un dossier ne peut pas être déplacé "
                "dans lui-même ou dans l'un de ses sous-dossiers."
            )

        shutil.move(
            str(source),
            str(destination),
        )

        return destination

    # =====================================================
    # Suppression interne
    #
    # Pas encore exposée à OpenAI.
    # =====================================================

    def delete(
        self,
        relative_path: str | Path,
    ) -> None:

        target = self.workspace_path(
            relative_path
        )

        if not target.exists():

            raise AtlasStorageNotFoundError(
                f"Chemin introuvable : {target}"
            )

        if target == self.root:

            raise AtlasStoragePermissionError(
                "La racine Atlas ne peut pas être supprimée."
            )

        if target.is_dir():

            shutil.rmtree(
                target
            )

        else:

            target.unlink()

    # =====================================================
    # Information
    # =====================================================

    def get_root(
        self,
    ) -> Path:

        return self.root