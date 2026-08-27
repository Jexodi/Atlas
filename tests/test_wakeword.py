import numpy as np

from atlas.audio.wakeword import (
    DummyWakeWordDetector,
)


def test_dummy_wakeword_never_detects():

    detector = DummyWakeWordDetector()

    samples = np.zeros(
        (960, 1),
        dtype=np.float32,
    )

    result = detector.process(
        samples,
        24000,
    )

    assert result is False