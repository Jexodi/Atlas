# Sideron.UI — Sideron Desktop

Interface principale native C# / WinUI 3 d'Sideron.

## Etat actuel

- surface Sideron Desktop sur le moniteur selectionne ;
- dock Sideron permanent ;
- explorateur Sideron multi-fenetres et multi-onglets ;
- parametres natifs ;
- widgets Core/Systeme ;
- lanceur d'applications ;
- applications externes synchronisees avec le bureau Sideron ;
- IPC local avec le Core Python ;
- demarrage et arret coordonnes du Core ;
- restauration de la barre des taches a la fermeture.

L'ancienne UI Python/PySide6, `MainWindow` et `WorkspaceArcControl` ont ete retires.

## Developpement

```powershell
cd C:\SIDERON\ui-native\SIDERON.UI
.\build.ps1
.\run.ps1
```

## Publication

```powershell
cd C:\SIDERON\ui-native\SIDERON.UI
.\publish.ps1
```

Le build complet UI + Core est orchestre par `installer\build_release.ps1`.
