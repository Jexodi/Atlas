import io
import wave

import numpy as np

from atlas.audio.utterance import AudioUtterance


def utterance_to_wav(
    utterance: AudioUtterance,
) -> io.BytesIO:

    samples = np.clip(
        utterance.samples,
        -1.0,
        1.0,
    )

    pcm16 = (
        samples * 32767
    ).astype(
        np.int16
    )

    buffer = io.BytesIO()

    with wave.open(
        buffer,
        "wb",
    ) as wav_file:

        wav_file.setnchannels(
            utterance.channels
        )

        wav_file.setsampwidth(
            2
        )

        wav_file.setframerate(
            utterance.sample_rate
        )

        wav_file.writeframes(
            pcm16.tobytes()
        )

    buffer.seek(0)

    buffer.name = "utterance.wav"

    return buffer