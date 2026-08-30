# Sideron Native UI

L'interface principale d'Sideron est maintenant native C# / WinUI 3.
L'ancienne interface Python/PySide6 a ete retiree.

Architecture actuelle :

- `Sideron.UI` : Sideron Desktop, fenetres internes, dock et parametres ;
- `main_core.py` : point d'entree du Core Python ;
- IPC local : communication Sideron.UI <-> Core ;
- SideronService : operations privilegiees validees par le Core ;
- Windows Speech : wake word local `Sideron`, sans modele externe.

Le build de release est realise par `installer\build_release.ps1`.
