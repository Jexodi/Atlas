from __future__ import annotations

import dataclasses
import json
import os
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

from atlas.core.event_bus import EventBus


class SideronUiBridge:
    """Pont IPC local non bloquant entre Sideron Core et Sideron.UI.

    Deux Named Pipes unidirectionnels sont utilisés :

    - SIDERON.CoreToUI.v1 : Core Python -> Sideron.UI
    - Sideron.UIToCore.v1 : Sideron.UI -> Core Python

    IMPORTANT :
    aucune écriture Named Pipe n'est effectuée depuis le thread
    principal du Core. Les messages sortants passent par une queue
    et sont écrits par un thread IPC dédié.

    Ainsi, Sideron continue de fonctionner même si l'UI est lente,
    absente, redémarre ou si Windows bloque momentanément un pipe.
    """

    CORE_TO_UI_PIPE_NAME = (
        "SIDERON.CoreToUI.v1"
    )

    UI_TO_CORE_PIPE_NAME = (
        "Sideron.UIToCore.v1"
    )

    CORE_TO_UI_PIPE_PATH = (
        rf"\\.\pipe\{CORE_TO_UI_PIPE_NAME}"
    )

    UI_TO_CORE_PIPE_PATH = (
        rf"\\.\pipe\{UI_TO_CORE_PIPE_NAME}"
    )

    RECONNECT_DELAY_SECONDS = 1.0

    OUTBOX_MAX_SIZE = 256

    _FORWARDED_EVENTS = (
        "ui.workspace.open_directory",
        "audio.speech_started",
        "audio.speech_ended",
        "ai.speech_started",
        "ai.speech_ended",
        "ai.realtime.connected",
        "ai.realtime.disconnected",
        "atlas.ready",
        "atlas.stopping",
    )

    def __init__(
        self,
        event_bus: EventBus,
        logger,
        state_provider: Callable[
            [],
            Any,
        ],
    ) -> None:

        self._event_bus = (
            event_bus
        )

        self._logger = logger

        self._state_provider = (
            state_provider
        )

        self._connection_thread: (
            threading.Thread
            | None
        ) = None

        self._writer_thread: (
            threading.Thread
            | None
        ) = None

        self._stop_event = (
            threading.Event()
        )

        self._connected = (
            threading.Event()
        )

        self._outbox: queue.Queue[
            dict[str, Any]
        ] = queue.Queue(
            maxsize=self.OUTBOX_MAX_SIZE
        )

        self._to_ui_pipe = None
        self._from_ui_pipe = None

        self._pipe_lock = (
            threading.Lock()
        )

        self._subscriptions_bound = (
            False
        )

        self._bound_handlers: dict[
            str,
            Callable[[Any], None],
        ] = {}

        self._last_unavailable_log = 0.0

    @property
    def connected(
        self,
    ) -> bool:

        return (
            self._connected.is_set()
        )

    def start(
        self,
    ) -> None:

        if (
            self._connection_thread is not None
            and self._connection_thread.is_alive()
        ):

            return

        self._stop_event.clear()

        self._bind_events()

        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="SideronUiBridgeWriter",
            daemon=True,
        )

        self._connection_thread = threading.Thread(
            target=self._connection_loop,
            name="SideronUiBridgeReader",
            daemon=True,
        )

        self._writer_thread.start()
        self._connection_thread.start()

        self._logger.info(
            "Pont Sideron.UI démarré "
            "(IPC non bloquant)."
        )

    def stop(
        self,
        timeout: float = 2.0,
    ) -> None:

        self._stop_event.set()

        self._connected.clear()

        self._close_pipes()

        # Réveille le writer s'il attend la queue.
        self._queue_internal(
            {
                "type": "_stop",
            }
        )

        for thread in (
            self._connection_thread,
            self._writer_thread,
        ):

            if (
                thread is not None
                and thread.is_alive()
            ):

                thread.join(
                    timeout=timeout
                )

        self._connection_thread = None
        self._writer_thread = None

        self._unbind_events()

        self._clear_outbox()

        self._logger.info(
            "Pont Sideron.UI arrêté."
        )

    def send_event(
        self,
        name: str,
        payload: Any = None,
    ) -> bool:
        """Place un événement dans la file d'envoi.

        Cette méthode ne réalise AUCUNE E/S Named Pipe.
        Elle est donc sûre à appeler depuis le thread principal Sideron.
        """

        if not self._connected.is_set():

            return False

        return self._queue_internal(
            {
                "type": "event",
                "name": name,
                "payload": self._json_safe(
                    payload
                ),
            }
        )

    def _queue_internal(
        self,
        message: dict[str, Any],
    ) -> bool:

        try:

            self._outbox.put_nowait(
                message
            )

            return True

        except queue.Full:

            self._logger.warning(
                "File IPC Sideron.UI pleine ; "
                "message abandonné."
            )

            return False

    def _connection_loop(
        self,
    ) -> None:

        while not self._stop_event.is_set():

            try:

                self._connect_once()

            except Exception as exc:

                if not self._stop_event.is_set():

                    now = time.monotonic()

                    if (
                        now
                        - self._last_unavailable_log
                        >= 5.0
                    ):

                        self._last_unavailable_log = (
                            now
                        )

                        self._logger.debug(
                            "Sideron.UI IPC indisponible : %s",
                            exc,
                        )

            finally:

                was_connected = (
                    self._connected.is_set()
                )

                self._connected.clear()

                self._close_pipes()

                self._clear_outbox()

                if was_connected:

                    self._logger.info(
                        "Sideron.UI IPC déconnecté."
                    )

            if not self._stop_event.is_set():

                self._stop_event.wait(
                    self.RECONNECT_DELAY_SECONDS
                )

    def _connect_once(
        self,
    ) -> None:

        write_flags = (
            os.O_WRONLY
            | getattr(
                os,
                "O_BINARY",
                0,
            )
        )

        read_flags = (
            os.O_RDONLY
            | getattr(
                os,
                "O_BINARY",
                0,
            )
        )

        to_ui_descriptor = os.open(
            self.CORE_TO_UI_PIPE_PATH,
            write_flags,
        )

        try:

            from_ui_descriptor = os.open(
                self.UI_TO_CORE_PIPE_PATH,
                read_flags,
            )

        except Exception:

            os.close(
                to_ui_descriptor
            )

            raise

        to_ui_pipe = os.fdopen(
            to_ui_descriptor,
            "wb",
            buffering=0,
        )

        from_ui_pipe = os.fdopen(
            from_ui_descriptor,
            "rb",
            buffering=0,
        )

        with self._pipe_lock:

            self._to_ui_pipe = (
                to_ui_pipe
            )

            self._from_ui_pipe = (
                from_ui_pipe
            )

        self._connected.set()

        self._logger.info(
            "Sideron Core connecté à Sideron.UI "
            "(2 pipes IPC non bloquants)."
        )

        self._queue_internal(
            {
                "type": "hello",
                "source": "core",
                "version": "3.3.6",
                "state": self._state_snapshot(),
            }
        )

        self.send_event(
            "atlas.status",
            self._state_snapshot(),
        )

        while not self._stop_event.is_set():

            with self._pipe_lock:

                pipe = (
                    self._from_ui_pipe
                )

            if pipe is None:

                break

            raw = pipe.readline()

            if not raw:

                break

            try:

                message = json.loads(
                    raw.decode(
                        "utf-8"
                    )
                )

            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
            ):

                self._logger.warning(
                    "Message Sideron.UI IPC invalide ignoré."
                )

                continue

            self._handle_message(
                message
            )

    def _writer_loop(
        self,
    ) -> None:

        while not self._stop_event.is_set():

            try:

                message = self._outbox.get(
                    timeout=0.5
                )

            except queue.Empty:

                continue

            try:

                if (
                    message.get(
                        "type"
                    ) == "_stop"
                ):

                    continue

                if not self._connected.is_set():

                    continue

                self._write_message(
                    message
                )

            finally:

                self._outbox.task_done()

    def _write_message(
        self,
        message: dict[str, Any],
    ) -> None:

        payload = (
            json.dumps(
                message,
                ensure_ascii=False,
                separators=(
                    ",",
                    ":",
                ),
            )
            + "\n"
        ).encode(
            "utf-8"
        )

        with self._pipe_lock:

            pipe = (
                self._to_ui_pipe
            )

            if pipe is None:

                return

            try:

                pipe.write(
                    payload
                )

            except (
                BrokenPipeError,
                OSError,
                ValueError,
            ) as exc:

                self._logger.debug(
                    "Échec envoi IPC Core -> Sideron.UI : %s",
                    exc,
                )

                self._connected.clear()

    def _handle_message(
        self,
        message: Any,
    ) -> None:

        if not isinstance(
            message,
            dict,
        ):

            return

        message_type = message.get(
            "type"
        )

        name = message.get(
            "name"
        )

        self._logger.debug(
            "IPC Sideron.UI -> Core : type=%s name=%s",
            message_type,
            name,
        )

        if message_type == "hello":

            self._logger.info(
                "Handshake Sideron.UI reçu."
            )

            return

        if (
            message_type == "command"
            and name == "atlas.ping"
        ):

            queued = self.send_event(
                "atlas.pong",
                {
                    "status": "ready",
                    "state": self._state_snapshot(),
                },
            )

            self._logger.info(
                "Ping Sideron.UI reçu ; "
                "pong mis en file=%s.",
                queued,
            )

            return

        if message_type == "command":

            self._event_bus.publish(
                "ui.native.command",
                {
                    "name": name,
                    "payload": self._json_safe(
                        message.get(
                            "payload"
                        )
                    ),
                },
            )

            self._logger.debug(
                "Commande Sideron.UI reçue : %s",
                name,
            )

    def _bind_events(
        self,
    ) -> None:

        if self._subscriptions_bound:
            return

        for event_name in (
            self._FORWARDED_EVENTS
        ):

            handler = self._make_event_handler(
                event_name
            )

            self._bound_handlers[
                event_name
            ] = handler

            self._event_bus.subscribe(
                event_name,
                handler,
            )

        self._subscriptions_bound = (
            True
        )

    def _unbind_events(
        self,
    ) -> None:

        for (
            event_name,
            handler,
        ) in self._bound_handlers.items():

            self._event_bus.unsubscribe(
                event_name,
                handler,
            )

        self._bound_handlers.clear()

        self._subscriptions_bound = (
            False
        )

    def _make_event_handler(
        self,
        event_name: str,
    ):

        def handler(
            payload=None,
        ) -> None:

            if event_name == "atlas.ready":

                payload = (
                    self._state_snapshot()
                )

            queued = self.send_event(
                event_name,
                payload,
            )

            if queued:

                self._logger.debug(
                    "IPC Core -> Sideron.UI mis en file : event=%s",
                    event_name,
                )

        return handler

    def _state_snapshot(
        self,
    ) -> dict[str, Any]:

        try:

            state = (
                self._state_provider()
            )

        except Exception:

            return {
                "status": "unknown",
            }

        result = self._json_safe(
            state
        )

        if isinstance(
            result,
            dict,
        ):

            return result

        return {
            "status": "unknown",
        }

    def _close_pipes(
        self,
    ) -> None:

        with self._pipe_lock:

            pipes = (
                self._to_ui_pipe,
                self._from_ui_pipe,
            )

            self._to_ui_pipe = None
            self._from_ui_pipe = None

        for pipe in pipes:

            if pipe is None:
                continue

            try:

                pipe.close()

            except OSError:

                pass

    def _clear_outbox(
        self,
    ) -> None:

        while True:

            try:

                self._outbox.get_nowait()

            except queue.Empty:

                break

            else:

                self._outbox.task_done()

    @classmethod
    def _json_safe(
        cls,
        value: Any,
        depth: int = 0,
    ) -> Any:

        if depth > 6:

            return str(
                value
            )

        if value is None:

            return None

        if isinstance(
            value,
            (
                str,
                int,
                float,
                bool,
            ),
        ):

            return value

        if dataclasses.is_dataclass(
            value
        ):

            return cls._json_safe(
                dataclasses.asdict(
                    value
                ),
                depth + 1,
            )

        if isinstance(
            value,
            dict,
        ):

            return {
                str(
                    key
                ): cls._json_safe(
                    item,
                    depth + 1,
                )
                for (
                    key,
                    item,
                ) in value.items()
            }

        if isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):

            return [
                cls._json_safe(
                    item,
                    depth + 1,
                )
                for item in value
            ]

        return str(
            value
        )
