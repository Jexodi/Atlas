import numpy as np

from atlas.audio.chunks import AudioChunk
from atlas.audio.utterance import (
    UtteranceBuffer,
)


def make_chunk(
    value: float = 0.1,
) -> AudioChunk:

    samples = np.full(
        (960, 1),
        value,
        dtype=np.float32,
    )

    return AudioChunk(
        samples=samples,
        sample_rate=24000,
        channels=1,
    )


def test_utterance_buffer_records():

    buffer = UtteranceBuffer()

    buffer.start()

    buffer.add(
        make_chunk()
    )

    buffer.add(
        make_chunk()
    )

    utterance = buffer.finish()

    assert utterance is not None

    assert utterance.samples.shape == (
        1920,
        1,
    )

    assert utterance.sample_rate == 24000
    assert utterance.channels == 1


def test_pre_roll_is_included():

    buffer = UtteranceBuffer()

    pre_roll = [
        make_chunk(),
        make_chunk(),
    ]

    buffer.start(
        pre_roll=pre_roll
    )

    buffer.add(
        make_chunk()
    )

    utterance = buffer.finish()

    assert utterance is not None

    assert len(
        utterance.samples
    ) == 2880


def test_finish_without_recording_returns_none():

    buffer = UtteranceBuffer()

    assert buffer.finish() is None