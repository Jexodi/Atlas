# Atlas 3.3.5-rc.2 — Audio et mises à jour

## Changements

- Voix et écoute : choix du microphone, appliqué à la capture et mémorisé immédiatement.
- Premier démarrage : périphérique d'entrée par défaut Windows. L'option « Par défaut Windows » résout à nouveau ce choix au démarrage du Core ou lors de sa sélection.
- Identifiant mémorisé : nom du micro et API audio (pas un index susceptible de changer). Deux périphériques de noms strictement identiques sur la même API ne sont pas distingués.
- Micro mémorisé absent au démarrage : repli explicite au défaut Windows. Un changement refusé restaure l'ancien flux si possible et affiche une erreur.
- Canal Experimental : RC strictement supérieure à la Release publiée ET à la version installée. Si la référence Release est inaccessible ou invalide, téléchargement RC bloqué.
- Canal Release : téléchargement disponible pour réinstaller la même version ou revenir à une stable plus ancienne.
- Notification des versions réellement plus récentes hors du menu Mises à jour, au plus une fois par version/canal et par session. Pas de notification pour une simple réinstallation. Vérification au démarrage et toutes les 30 minutes lorsque l'application tourne.
- Sélection du canal verrouillée pendant téléchargement/installation ; conservation des contrôles SHA-256 et du rollback existants.

## Compilation obligatoire sous Windows

Depuis la racine de ce projet, avec les dépendances habituelles :

```powershell
.\installer\build_release.ps1
.\installer\build_installer_launcher.ps1
```

Ne pas utiliser `-SkipBuild` pour cette première compilation : un ancien EXE n'intègre pas ces changements.
L'archive contient les sources, pas une distribution compilée ni un ancien payload.zip. Le lanceur régénère et valide son payload.
Le manifeste RC est un brouillon sans URL/SHA-256 : le script de publication doit le compléter à partir du nouvel EXE. Ne pas publier ce brouillon tel quel. Le manifeste Release existant est conservé.

Attention : selon l'ordre des versions, `3.3.5-rc.2 < 3.3.5`. Installer cette RC manuellement pour l'essayer si la Release publiée est déjà 3.3.5. Une future `3.3.6-rc.1` sera supérieure à `3.3.5` et éligible.

## Contrôles disponibles

Réussis dans l'environnement de préparation : compilation syntaxique des modules Python, 7 tests simulés du microphone, lecture XML des XAML/projets et JSON de configuration.

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover -s tests -p test_rc2_microphone.py -v
dotnet run --project .\tests\UpdatePolicy\UpdatePolicy.csproj
```

Le test .NET contient 8 cas et utilise le véritable service avec un transport HTTP simulé (aucune publication). Il n'a pas été exécuté ici : .NET et Windows ne sont pas disponibles. La suite pytest générale n'a pas été exécutée.

## Recette Windows restant à faire

1. Profil neuf : vérifier le micro par défaut Windows, puis enregistrer avec deux micros différents.
2. Changer de micro pendant l'écoute, en modes continu et wake word ; vérifier la vraie source audio, pas seulement le libellé.
3. Redémarrer Atlas/Core : vérifier le choix persistant. Modifier le canal puis le micro : vérifier que le canal reste conservé.
4. Débrancher le micro mémorisé puis redémarrer : vérifier le repli et l'avertissement. Un branchement à chaud peut nécessiter un redémarrage du Core pour actualiser PortAudio.
5. Simuler un micro occupé/incompatible : vérifier l'erreur et la reprise de l'ancien micro. Si aucun micro n'était disponible au lancement, brancher puis redémarrer le Core.
6. RC sous la Release : téléchargement interdit. RC supérieure aux deux références : téléchargement proposé. Serveur Release indisponible : RC bloquée.
7. Release égale/inférieure à l'installation : téléchargement et réinstallation/restauration possibles après validation SHA-256.
8. Nouvelle version hors menu : popup ; « Plus tard » ne répète pas la popup durant la session. Dans le menu Mises à jour : pas de popup.
9. Tester les changements rapides de canal et une vérification pendant téléchargement. Valider installation, rollback et redémarrage sous Windows.

Ne déclarer les tâches Notion terminées qu'après cette recette.
