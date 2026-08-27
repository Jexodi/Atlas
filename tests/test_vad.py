from atlas.audio.vad import (
    VADState,
    VoiceActivityDetector,
)


def test_vad_starts_speech():

    vad = VoiceActivityDetector(
        threshold_db=-35,
        start_duration_ms=100,
        end_silence_ms=500,
    )

    assert vad.process(
        -60,
        now=0.0,
    ).speech_started is False

    assert vad.process(
        -20,
        now=1.0,
    ).speech_started is False

    event = vad.process(
        -20,
        now=1.11,
    )

    assert event.speech_started is True

    assert vad.state == VADState.SPEECH


def test_vad_ends_speech():

    vad = VoiceActivityDetector(
        threshold_db=-35,
        start_duration_ms=100,
        end_silence_ms=500,
    )

    vad.process(
        -20,
        now=1.0,
    )

    vad.process(
        -20,
        now=1.11,
    )

    event = vad.process(
        -60,
        now=1.3,
    )

    assert event.speech_ended is False

    event = vad.process(
        -60,
        now=1.7,
    )

    assert event.speech_ended is True

    assert vad.state == VADState.SILENCE


def test_short_noise_does_not_start_speech():

    vad = VoiceActivityDetector(
        threshold_db=-35,
        start_duration_ms=150,
        end_silence_ms=500,
    )

    vad.process(
        -20,
        now=1.0,
    )

    vad.process(
        -60,
        now=1.05,
    )

    assert vad.state == VADState.SILENCE