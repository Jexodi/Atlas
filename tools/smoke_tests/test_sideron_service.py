from atlas.service import (
    SideronServiceClient,
    SideronServiceError,
)


def main() -> None:

    print()
    print(
        "=== TEST SIDERON SERVICE ==="
    )
    print()

    client = (
        SideronServiceClient()
    )

    try:

        response = (
            client.ping()
        )

    except SideronServiceError as exc:

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
            "❌ SideronService a refusé la requête."
        )


if __name__ == "__main__":

    main()