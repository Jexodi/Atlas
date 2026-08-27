# Atlas.UI — Atlas Desktop

Interface principale native C# / WinUI 3 d'Atlas.

## Etat actuel

- surface Atlas Desktop sur le moniteur selectionne ;
- dock Atlas permanent ;
- explorateur Atlas multi-fenetres et multi-onglets ;
- parametres natifs ;
- widgets Core/Systeme ;
- lanceur d'applications ;
- applications externes synchronisees avec le bureau Atlas ;
- IPC local avec le Core Python ;
- demarrage et arret coordonnes du Core ;
- restauration de la barre des taches a la fermeture.

L'ancienne UI Python/PySide6, `MainWindow` et `WorkspaceArcControl` ont ete retires.

## Developpement

```powershell
cd C:\Atlas\ui-native\Atlas.UI
.\build.ps1
.\run.ps1
```

## Publication

```powershell
cd C:\Atlas\ui-native\Atlas.UI
.\publish.ps1
```

Le build complet UI + Core est orchestre par `installer\build_release.ps1`.
