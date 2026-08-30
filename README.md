# SIDERON

**S**ystem for **I**ntelligent **D**ialogue, **E**xecution, **R**easoning, **O**perations and **N**avigation.

SIDERON est un assistant personnel natif pour Windows, orienté interaction vocale, automatisation locale et pilotage sécurisé du poste. L’interface de bureau est développée en C# / WinUI 3 et le Core intelligent en Python.

> État actuel : `3.3.6` — Release Candidate du canal expérimental.

## Fonctionnalités

- interface Windows plein écran avec dock, widgets et présence dans la barre des tâches ;
- interaction vocale continue ou par mot de réveil ;
- sélection séparée du microphone et de la sortie audio ;
- utilisation automatique du périphérique Windows par défaut au premier démarrage ;
- télémétrie locale du système, du réseau et du stockage ;
- espace de travail isolé avec import, lecture et gestion de fichiers ;
- actions système soumises à une politique de permissions ;
- canaux de mise à jour `release`, `rc` et `dev` ;
- notification automatique lorsqu’une mise à jour est disponible ;
- installateur transactionnel avec contrôle SHA-256 et rollback automatique ;
- service Windows privilégié limité à l’utilisateur autorisé.

## Prérequis de développement

- Windows 10 version 1809 ou supérieure, ou Windows 11 ;
- PowerShell 5.1 ou PowerShell 7 ;
- Python 3.12 x64 ;
- .NET 8 SDK ;
- Git et GitHub CLI pour la publication.

## Installation pour les utilisateurs

Téléchargez l’installateur correspondant à votre canal depuis les [Releases GitHub](https://github.com/Jexodi/SIDERON/releases), puis exécutez-le en administrateur.

L’installation utilise les emplacements suivants :

| Élément | Emplacement |
| --- | --- |
| Application | `C:\Program Files\SIDERON` |
| Configuration utilisateur | `%LOCALAPPDATA%\SIDERON\config\sideron.json` |
| Journaux utilisateur | `%LOCALAPPDATA%\SIDERON\logs` |
| Configuration du service | `%PROGRAMDATA%\SIDERON` |
| Données par défaut | `C:\SIDERON` |

Lors d’une migration depuis Atlas, SIDERON reconnaît l’ancienne installation, récupère sa configuration et conserve le stockage `C:\Atlas` ou un volume dédié portant encore le label `ATLAS`. Aucune donnée utilisateur n’est supprimée ou reformatée automatiquement.

## Démarrage en développement

Créez l’environnement Python puis installez les dépendances :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,packaging]"
```

Copiez ensuite `.env.example` vers `.env` uniquement si votre environnement requiert une configuration locale. Ne publiez jamais `.env`, une clé API, un jeton GitHub ou un secret du relais.

Pour compiler et lancer uniquement l’interface :

```powershell
Set-Location .\ui-native\Sideron.UI
.\build.ps1
.\run.ps1
```

## Construction de l’installateur

Depuis la racine du projet :

```powershell
.\installer\build_release.ps1
.\installer\build_installer_launcher.ps1
```

Le premier script construit l’interface, le Core et le service. Le second régénère et vérifie intégralement le payload avant de produire `SIDERON-<version>.exe`.

## Publication GitHub

La version et le canal sont lus automatiquement depuis `config\sideron.json`. Les scripts créent la Release ou pré-release GitHub, téléversent l’installateur, calculent son SHA-256 puis publient le manifeste correspondant.

```powershell
# Release Candidate
.\Publish-SIDERONRC.ps1

# Release stable
.\Publish-SIDERONRelease.ps1

# Version de développement
.\Publish-SIDERONDev.ps1
```

Pour réutiliser un installateur déjà construit :

```powershell
.\Publish-SIDERONRC.ps1 -SkipBuild
```

Les paramètres `-SkipGitHubPublication` et `-OpenGitHubReleasePage` restent disponibles. Avant la première publication, renommez le dépôt GitHub `Atlas` en `SIDERON` ou passez explicitement `-GitHubRepository` aux scripts.

## Canaux de mise à jour

| Canal | Format de version | Manifeste | Publication GitHub |
| --- | --- | --- | --- |
| Release | `3.3.5` | `updates/manifests/release.json` | Release stable |
| RC / Expérimental | `3.3.5-rc.1` | `updates/manifests/rc.json` | Pré-release |
| Dev | `3.3.6-dev.1` | `updates/manifests/dev.json` | Pré-release |

## Organisation du projet

```text
config/                 Configuration distribuée
installer/              Build, installation, mise à jour et désinstallation
service/                Hôte du service Windows privilégié
src/atlas/              Package Python interne conservé pour compatibilité
tests/                  Tests Python et politique de mise à jour
ui-native/Sideron.UI/   Interface WinUI 3
updates/manifests/      Manifestes des trois canaux
```

Le nom interne du package Python reste temporairement `atlas`. Cette compatibilité n’est pas visible par l’utilisateur et évite de casser les extensions et imports existants pendant la migration de marque.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
dotnet run --project .\tests\UpdatePolicy\UpdatePolicy.csproj
```

## Sécurité

- aucun secret ne doit être versionné ;
- les téléchargements sont validés par SHA-256 avant installation ;
- une mise à jour défaillante restaure automatiquement la version précédente ;
- le service privilégié valide l’identité de l’utilisateur et les commandes autorisées ;
- la suppression des données reste une action explicite lors de la désinstallation.

## Licence

Aucune licence open source n’est encore déclarée. Tant qu’un fichier `LICENSE` n’est pas ajouté, le code reste sous droits réservés.
