import asyncio
from collections.abc import Awaitable, Callable


BackgroundTask = Callable[[], Awaitable[None]]


class LifecycleManager:

    def __init__(self, logger) -> None:
        self.logger = logger

        self._tasks: dict[
            str,
            asyncio.Task,
        ] = {}

        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:

        self._running = True

        self.logger.info(
            "LifecycleManager démarré."
        )

    async def stop(self) -> None:

        if not self._running:
            return

        self.logger.info(
            "Arrêt des tâches d'arrière-plan..."
        )

        self._running = False

        for task in self._tasks.values():
            task.cancel()

        if self._tasks:

            await asyncio.gather(
                *self._tasks.values(),
                return_exceptions=True,
            )

        self._tasks.clear()

        self.logger.info(
            "LifecycleManager arrêté."
        )

    def create_task(
        self,
        name: str,
        coroutine: Awaitable[None],
    ) -> None:

        if name in self._tasks:
            raise ValueError(
                f"La tâche '{name}' existe déjà."
            )

        task = asyncio.create_task(
            coroutine,
            name=name,
        )

        self._tasks[name] = task

        task.add_done_callback(
            lambda completed_task: (
                self._on_task_done(
                    name,
                    completed_task,
                )
            )
        )

        self.logger.debug(
            "Tâche créée : %s",
            name,
        )

    def _on_task_done(
        self,
        name: str,
        task: asyncio.Task,
    ) -> None:

        self._tasks.pop(
            name,
            None,
        )

        if task.cancelled():
            self.logger.debug(
                "Tâche annulée : %s",
                name,
            )
            return

        exception = task.exception()

        if exception is not None:
            self.logger.error(
                "La tâche '%s' a échoué : %s",
                name,
                exception,
                exc_info=exception,
            )