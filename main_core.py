import asyncio
import signal
import sys
from pathlib import Path


ROOT = Path(
    __file__
).resolve().parent

SRC = (
    ROOT
    / "src"
)

sys.path.insert(
    0,
    str(
        SRC
    ),
)


from atlas.core.application import (
    SideronApplication,
)


async def run_core() -> None:

    atlas = SideronApplication()

    stop_event = (
        asyncio.Event()
    )

    loop = (
        asyncio.get_running_loop()
    )

    def request_stop(
        *args,
    ) -> None:

        if not stop_event.is_set():

            stop_event.set()

    def handle_native_ui_command(
        payload=None,
    ) -> None:

        if not isinstance(
            payload,
            dict,
        ):
            return

        if (
            payload.get(
                "name"
            )
            != "atlas.shutdown_core"
        ):
            return

        loop.call_soon_threadsafe(
            request_stop
        )

    atlas.events.subscribe(
        "ui.native.command",
        handle_native_ui_command,
    )

    for signal_name in (
        signal.SIGINT,
        signal.SIGTERM,
    ):

        try:

            loop.add_signal_handler(
                signal_name,
                request_stop,
            )

        except (
            NotImplementedError,
            RuntimeError,
        ):

            # add_signal_handler n'est pas disponible
            # sur toutes les boucles Windows.
            pass

    await atlas.initialize()

    print(
        "Sideron Core prêt. "
        "Ctrl+C pour arrêter."
    )

    try:

        await stop_event.wait()

    except KeyboardInterrupt:

        pass

    finally:

        await atlas.shutdown()


def main() -> None:

    try:

        asyncio.run(
            run_core()
        )

    except KeyboardInterrupt:

        pass


if __name__ == "__main__":

    main()
