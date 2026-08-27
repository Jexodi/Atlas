import asyncio
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from atlas.audio.chunks import AudioChunk


ChunkCallback = Callable[[AudioChunk], None]


class MicrophoneCapture:

    def __init__(
        self,
        logger,
        device_index: int | None = None,
        sample_rate: int = 24000,
        channels: int = 1,
        block_size: int = 960,
    ) -> None:

        self.logger = logger

        self.device_index = device_index
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size

        self._stream = None
        self._running = False

        self._chunk_callback: (
            ChunkCallback | None
        ) = None

    @property
    def running(self) -> bool:
        return self._running

    def set_chunk_callback(
        self,
        callback: ChunkCallback,
    ) -> None:

        self._chunk_callback = callback

    def _audio_callback(
        self,
        indata,
        frames,
        time_info,
        status,
    ) -> None:

        if status:
            self.logger.debug(
                "Audio status : %s",
                status,
            )

        if len(indata) == 0:
            return

        if self._chunk_callback is None:
            return

        samples = np.array(
            indata,
            dtype=np.float32,
            copy=True,
        )

        chunk = AudioChunk(
            samples=samples,
            sample_rate=self.sample_rate,
            channels=self.channels,
        )

        self._chunk_callback(
            chunk
        )

    async def run(self) -> None:

        if self._running:
            return

        self.logger.info(
            "Démarrage de la capture microphone."
        )

        self._stream = sd.InputStream(
            device=self.device_index,
            channels=self.channels,
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            dtype="float32",
            callback=self._audio_callback,
        )

        self._stream.start()

        self._running = True

        try:

            while True:
                await asyncio.sleep(1)

        except asyncio.CancelledError:

            self.logger.info(
                "Arrêt de la capture microphone."
            )

            raise

        finally:

            self.stop()

    def stop(self) -> None:

        if self._stream is not None:

            try:
                self._stream.stop()
                self._stream.close()

            finally:
                self._stream = None

        self._running = False