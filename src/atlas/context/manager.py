import asyncio

from atlas.context.models import AtlasContext
from atlas.context.system_context import (
    SystemContextProvider,
)
from atlas.context.windows_context import (
    WindowsContextProvider,
)
from atlas.core.event_bus import EventBus


class ContextManager:

    def __init__(
        self,
        event_bus: EventBus,
        logger,
    ) -> None:

        self.event_bus = event_bus
        self.logger = logger

        self.system_provider = (
            SystemContextProvider()
        )

        self.windows_provider = (
            WindowsContextProvider()
        )

        self.context = AtlasContext()

    def refresh(self) -> AtlasContext:

        previous_window = (
            self.context.window.active_window_title
        )

        self.context.system = (
            self.system_provider.collect()
        )

        self.context.window = (
            self.windows_provider.collect()
        )

        current_window = (
            self.context.window.active_window_title
        )

        if current_window != previous_window:

            self.event_bus.publish(
                "context.active_window_changed",
                {
                    "previous": previous_window,
                    "current": current_window,
                    "process": (
                        self.context
                        .window
                        .active_process_name
                    ),
                },
            )

        return self.context

    def get_context(
        self,
    ) -> AtlasContext:

        return self.context

    async def run(
        self,
        interval: float = 1.0,
    ) -> None:

        self.logger.info(
            "Surveillance du contexte démarrée."
        )

        try:

            while True:

                self.refresh()

                await asyncio.sleep(
                    interval
                )

        except asyncio.CancelledError:

            self.logger.info(
                "Surveillance du contexte arrêtée."
            )

            raise
        