from pathlib import Path

from atlas.storage import (
    AtlasStorage,
    AtlasStoragePermissionError,
)


def main():

    print()
    print("=== TEST ATLAS STORAGE ===")
    print()

    storage = AtlasStorage(
        r"C:\Atlas"
    )

    storage.initialize()

    print(
        "Root :",
        storage.get_root(),
    )

    print()

    # =====================================================
    # Test création interne
    # =====================================================

    test_folder = (
        storage.create_directory(
            "Documents/Test"
        )
    )

    print(
        "Dossier créé :",
        test_folder,
    )

    # =====================================================
    # Test écriture interne
    # =====================================================

    test_file = (
        storage.write_text(
            "Documents/Test/atlas_test.txt",
            "Bonjour depuis AtlasStorage.",
            overwrite=True,
        )
    )

    print(
        "Fichier créé :",
        test_file,
    )

    # =====================================================
    # Test lecture
    # =====================================================

    content = (
        storage.read_text(
            test_file
        )
    )

    print(
        "Contenu :",
        content,
    )

    # =====================================================
    # Test de tentative d'évasion
    # =====================================================

    print()
    print(
        "Test tentative sortie Workspace..."
    )

    try:

        storage.write_text(
            r"..\Windows\atlas_interdit.txt",
            "Ceci ne doit jamais fonctionner.",
        )

        print(
            "❌ ERREUR : sécurité contournée."
        )

    except AtlasStoragePermissionError as exc:

        print(
            "✅ Sortie Workspace bloquée :",
            exc,
        )

    # =====================================================
    # Test chemin Windows absolu
    # =====================================================

    print()
    print(
        "Test chemin absolu..."
    )

    try:

        storage.workspace_path(
            r"C:\Windows\System32"
        )

        print(
            "❌ ERREUR : chemin absolu accepté."
        )

    except AtlasStoragePermissionError as exc:

        print(
            "✅ Chemin absolu bloqué :",
            exc,
        )

    print()
    print(
        "=== TEST TERMINÉ ==="
    )


if __name__ == "__main__":
    main()
