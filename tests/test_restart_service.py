from atlas.service import (
    AtlasServiceClient,
    AtlasServiceError,
)


def main() -> None:

    print()
    print(
        "=== TEST SERVICE.RESTART ==="
    )
    print()

    client = (
        AtlasServiceClient()
    )

    service_name = "Spooler"

    print(
        "Service testé :",
        service_name,
    )

    print()

    try:

        response = (
            client.restart_service(
                service_name
            )
        )

    except AtlasServiceError as exc:

        print(
            "❌ Erreur AtlasService :",
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
        "Error code :",
        response.error_code,
    )

    print(
        "Data :",
        response.data,
    )

    print()

    if response.success:

        print(
            "✅ Le redémarrage du service a fonctionné."
        )

    else:

        print(
            "❌ AtlasService a refusé ou échoué "
            "pendant le redémarrage."
        )


if __name__ == "__main__":

    main()