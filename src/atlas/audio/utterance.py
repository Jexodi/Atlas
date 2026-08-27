from dataclasses import dataclass

import numpy as np

from atlas.audio.chunks import AudioChunk


@dataclass(slots=True)
class AudioUtterance:
    samples: np.ndarray
    sample_rate: int
    channels: int
    duration_seconds: float


class UtteranceBuffer:

    def __init__(
        self,
    ) -> None:

        self._chunks: list[
            AudioChunk
        ] = []

        self._recording = False

    @property
    def recording(self) -> bool:
        return self._recording

    def start(
        self,
        pre_roll: list[AudioChunk] | None = None,
    ) -> None:

        self._chunks.clear()

        if pre_roll:

            self._chunks.extend(
                pre_roll
            )

        self._recording = True

    def add(
        self,
        chunk: AudioChunk,
    ) -> None:

        if not self._recording:
            return

        self._chunks.append(
            chunk
        )

    def finish(
        self,
    ) -> AudioUtterance | None:

        if not self._recording:
            return None

        self._recording = False

        if not self._chunks:
            return None

        first_chunk = self._chunks[0]

        samples = np.concatenate(
            [
                chunk.samples
                for chunk in self._chunks
            ],
            axis=0,
        )

        sample_rate = (
            first_chunk.sample_rate
        )

        channels = (
            first_chunk.channels
        )

        duration_seconds = (
            len(samples)
            / sample_rate
        )

        utterance = AudioUtterance(
            samples=samples,
            sample_rate=sample_rate,
            channels=channels,
            duration_seconds=duration_seconds,
        )

        self._chunks.clear()

        return utterance

    def reset(
        self,
    ) -> None:

        self._chunks.clear()

        self._recording = False