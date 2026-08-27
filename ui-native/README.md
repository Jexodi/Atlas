# Atlas Native UI

L'interface principale d'Atlas est maintenant native C# / WinUI 3.
L'ancienne interface Python/PySide6 a ete retiree.

Architecture actuelle :

- `Atlas.UI` : Atlas Desktop, fenetres internes, dock et parametres ;
- `main_core.py` : point d'entree du Core Python ;
- IPC local : communication Atlas.UI <-> Core ;
- AtlasService : operations privilegiees validees par le Core ;
- Windows Speech : wake word local `Atlas`, sans modele externe.

Le build de release est realise par `installer\build_release.ps1`.
