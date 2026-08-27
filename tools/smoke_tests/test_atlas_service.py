from atlas.service import (
    AtlasServiceClient,
    AtlasServiceError,
)


def main() -> None:

    print()
    print(
        "=== TEST ATLAS SERVICE ==="
    )
    print()

    client = (
        AtlasServiceClient()
    )

    try:

        response = (
            client.ping()
        )

    except AtlasServiceError as exc:

        print(
            "❌ Communication impossible :",
            exc,
        )

        return

    print(
        "Success :",
        response.success,
    )

    print(
        "Message :",
        response.message,
    )

    print(
        "Data :",
        response.data,
    )

    if response.success:

        print()
        print(
            "✅ Communication IPC fonctionnelle."
        )

    else:

        print()
        print(
            "❌ AtlasService a refusé la requête."
        )


if __name__ == "__main__":

    main()