from atlas.service import (
    SideronServiceClient,
    SideronServiceError,
)


def main() -> None:

    print()
    print(
        "=== TEST SERVICE.RESTART ==="
    )
    print()

    client = (
        SideronServiceClient()
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

    except SideronServiceError as exc:

        print(
            "❌ Erreur SideronService :",
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
            "❌ SideronService a refusé ou échoué "
            "pendant le redémarrage."
        )


if __name__ == "__main__":

    main()