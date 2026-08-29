from atlas.service import (
    SideronServiceClient,
    SideronServiceError,
)


SERVICE_NAME = "Spooler"


def show_response(
    title,
    response,
) -> None:

    print()
    print(
        f"=== {title} ==="
    )

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


def main() -> None:

    client = (
        SideronServiceClient()
    )

    print()
    print(
        "=== TEST START / STOP SERVICE ==="
    )

    print(
        "Service :",
        SERVICE_NAME,
    )

    try:

        stop_response = (
            client.stop_service(
                SERVICE_NAME
            )
        )

        show_response(
            "STOP",
            stop_response,
        )

        if not stop_response.success:

            return

        input(
            "\nAppuie sur Entrée pour "
            "redémarrer le service..."
        )

        start_response = (
            client.start_service(
                SERVICE_NAME
            )
        )

        show_response(
            "START",
            start_response,
        )

    except SideronServiceError as exc:

        print()
        print(
            "❌ SideronService error :",
            exc,
        )


if __name__ == "__main__":

    main()