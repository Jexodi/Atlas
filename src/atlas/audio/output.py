import asyncio
import math
import threading

import numpy as np
import sounddevice as sd

class AudioOutput:

    def __init__(
        self,
        logger,
        device_index: int | None = None,
        sample_rate: int = 24000,
        channels: int = 1,
        echo_guard=None,
    ) -> None:

        self.logger = logger

        self.device_index = device_index
        self.sample_rate = sample_rate
        self.channels = channels
        self.echo_guard = echo_guard

        self.current_item_id: str | None = None
        self.played_samples = 0

        self.speaking = False
        self._output_level_db = -100.0

        self._stream = None
        self._running = False

        self._buffer = bytearray()
        self._lock = threading.Lock()

        self._response_done = False

        self._event_loop: (
            asyncio.AbstractEventLoop | None
        ) = None

        self._drained_event: (
            asyncio.Event | None
        ) = None

    def set_event_loop(
        self,
        loop: asyncio.AbstractEventLoop,
    ) -> None:

        self._event_loop = loop
        self._drained_event = asyncio.Event()

        self._drained_event.set()

    @property
    def output_level_db(
        self,
    ) -> float:

        with self._lock:

            return self._output_level_db

    async def run(self) -> None:

        if self._running:
            return

        self.logger.info(
            "Démarrage de la sortie audio Atlas."
        )

        self._stream = sd.RawOutputStream(
            device=self.device_index,
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            callback=self._audio_callback,
        )

        self._stream.start()
        self._running = True

        try:

            while True:
                await asyncio.sleep(1)

        except asyncio.CancelledError:

            self.logger.info(
                "Arrêt de la sortie audio Atlas."
            )

            raise

        finally:

            self.stop()

    def _audio_callback(
        self,
        outdata,
        frames,
        time_info,
        status,
    ) -> None:

        if status:

            self.logger.debug(
                "AudioOutput status : %s",
                status,
            )

        bytes_needed = (
            frames
            * self.channels
            * 2
        )

        with self._lock:

            available = len(
                self._buffer
            )

            bytes_to_copy = min(
                available,
                bytes_needed,
            )

            if bytes_to_copy > 0:

                outdata[
                    :bytes_to_copy
                ] = self._buffer[
                    :bytes_to_copy
                ]

                del self._buffer[
                    :bytes_to_copy
                ]

                sample_count = (
                    bytes_to_copy
                    // 2
                    // self.channels
                )

                self.played_samples += (
                    sample_count
                )

                if bytes_to_copy > 0:

                    played_audio = bytes(
                        outdata[
                            :bytes_to_copy
                        ]
                    )

                    # Niveau réel de la voix Atlas.
                    samples = np.frombuffer(
                        played_audio,
                        dtype="<i2",
                    ).astype(
                        np.float32
                    )

                    if samples.size > 0:

                        samples /= 32768.0

                        rms = float(
                            np.sqrt(
                                np.mean(
                                    samples * samples
                                )
                            )
                        )

                        level_db = (
                            20.0
                            * math.log10(
                                max(
                                    rms,
                                    1e-6,
                                )
                            )
                        )

                        # Lissage pour éviter une animation
                        # trop nerveuse.
                        self._output_level_db += (
                            level_db
                            - self._output_level_db
                        ) * 0.35

                    if self.echo_guard is not None:

                        self.echo_guard.feed_output(
                            played_audio
                        )

            if bytes_to_copy < bytes_needed:

                outdata[
                    bytes_to_copy:
                ] = bytes(
                    bytes_needed
                    - bytes_to_copy
                )

            if bytes_to_copy == 0:

                self._output_level_db += (
                    -100.0
                    - self._output_level_db
                ) * 0.25

            drained = (
                self._response_done
                and not self._buffer
            )

        if drained:

            self.speaking = False

            if (
                self._event_loop
                is not None
            ):

                self._event_loop.call_soon_threadsafe(
                    self._mark_drained
                )

    def _mark_drained(
        self,
    ) -> None:

        if self._drained_event is not None:
            self._drained_event.set()

    def enqueue(
        self,
        audio_data: bytes,
    ) -> None:

        if not audio_data:
            return

        with self._lock:

            self._buffer.extend(
                audio_data
            )

        self.speaking = True

    def start_response(
        self,
        item_id: str,
    ) -> None:

        self.current_item_id = item_id

        self.played_samples = 0
        self._response_done = False
        self.speaking = True

        if self._drained_event is not None:
            self._drained_event.clear()

    def mark_response_done(
        self,
    ) -> None:

        self._response_done = True

        with self._lock:
            empty = not self._buffer

        if empty:
            self.speaking = False
            self._mark_drained()

    async def wait_until_drained(
        self,
    ) -> None:

        if self._drained_event is None:
            return

        await self._drained_event.wait()

    def clear(
        self,
    ) -> None:

        with self._lock:

            self._buffer.clear()

            self._output_level_db = -100.0

        self._response_done = True
        self.speaking = False

        if self._stream is not None:

            try:

                self._stream.abort()
                self._stream.start()

            except Exception:

                self.logger.exception(
                    "Impossible d'interrompre "
                    "la sortie audio."
                )

        self._mark_drained()

    def get_played_duration_ms(
        self,
    ) -> int:

        if self.sample_rate <= 0:
            return 0

        return int(
            (
                self.played_samples
                / self.sample_rate
            )
            * 1000
        )

    def stop(self) -> None:

        if self._stream is not None:

            try:

                self._stream.stop()
                self._stream.close()

            finally:

                self._stream = None

        self._running = False
        self.speaking = False

        with self._lock:

            self._output_level_db = -100.0





        