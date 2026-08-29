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

    def switch_device(self, device_index):
        """Keep the capture task alive; restore the previous stream on failure."""
        previous = self.device_index
        was_running = self._running
        if not was_running:
            raise RuntimeError("Capture inactive : redémarrez le Core avant de changer de micro.")
        self.stop()
        try:
            self._open_device(device_index)
        except Exception as error:
            try:
                self._open_device(previous)
            except Exception:
                raise RuntimeError("Microphone indisponible et restauration impossible. Redémarrez le Core.") from error
            raise RuntimeError("Impossible d’ouvrir ce microphone ; ancien micro restauré.") from error

    def _open_device(self, index):
        stream = sd.InputStream(
            device=index, channels=self.channels, samplerate=self.sample_rate,
            blocksize=self.block_size, dtype="float32", callback=self._audio_callback,
        )
        try:
            stream.start()
        except Exception:
            stream.close()
            raise
        self._stream = stream
        self.device_index = index
        self._running = True
