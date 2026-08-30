from dataclasses import dataclass
from pathlib import Path
from typing import Literal


StorageEntryType = Literal[
    "file",
    "directory",
]


@dataclass(slots=True)
class StorageEntry:
    """
    Représente un fichier ou un dossier trouvé par Sideron.
    """

    name: str
    path: Path
    entry_type: StorageEntryType
    size: int | None = None

    @property
    def is_file(self) -> bool:
        return self.entry_type == "file"

    @property
    def is_directory(self) -> bool:
        return self.entry_type == "directory"


@dataclass(slots=True)
class ImportResult:
    """
    Résultat d'une copie depuis l'extérieur
    vers le Workspace Sideron.
    """

    source: Path
    destination: Path
    copied: bool