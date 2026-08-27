from collections import defaultdict
from collections.abc import Callable
from typing import Any


EventHandler = Callable[[Any], None]


class EventBus:

    def __init__(self):
        self._listeners: dict[
            str,
            list[EventHandler]
        ] = defaultdict(list)

    def subscribe(
        self,
        event_name: str,
        handler: EventHandler
    ) -> None:

        self._listeners[event_name].append(handler)

    def unsubscribe(
        self,
        event_name: str,
        handler: EventHandler
    ) -> None:

        if event_name not in self._listeners:
            return

        if handler in self._listeners[event_name]:
            self._listeners[event_name].remove(handler)

    def publish(
        self,
        event_name: str,
        payload: Any = None
    ) -> None:

        handlers = self._listeners.get(
            event_name,
            []
        )

        for handler in handlers:
            handler(payload)