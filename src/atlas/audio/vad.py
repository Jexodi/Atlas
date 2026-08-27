import time
from dataclasses import dataclass
from enum import Enum


class VADState(str, Enum):
    SILENCE = "silence"
    SPEECH = "speech"


@dataclass(slots=True)
class VADEvent:
    speech_started: bool = False
    speech_ended: bool = False


class VoiceActivityDetector:

    def __init__(
        self,
        threshold_db: float = -35.0,
        start_duration_ms: int = 120,
        end_silence_ms: int = 700,
    ) -> None:

        self.threshold_db = threshold_db

        self.start_duration = (
            start_duration_ms / 1000
        )

        self.end_silence = (
            end_silence_ms / 1000
        )

        self.state = VADState.SILENCE

        self._voice_start_candidate: (
            float | None
        ) = None

        self._last_voice_time: (
            float | None
        ) = None

    def process(
        self,
        level_db: float,
        now: float | None = None,
    ) -> VADEvent:

        if now is None:
            now = time.monotonic()

        event = VADEvent()

        voice_detected = (
            level_db >= self.threshold_db
        )

        if self.state == VADState.SILENCE:

            if voice_detected:

                if self._voice_start_candidate is None:
                    self._voice_start_candidate = now

                duration = (
                    now
                    - self._voice_start_candidate
                )

                if duration >= self.start_duration:

                    self.state = VADState.SPEECH

                    self._last_voice_time = now

                    self._voice_start_candidate = None

                    event.speech_started = True

            else:

                self._voice_start_candidate = None

            return event

        if self.state == VADState.SPEECH:

            if voice_detected:

                self._last_voice_time = now

                return event

            if self._last_voice_time is None:

                self._last_voice_time = now

                return event

            silence_duration = (
                now
                - self._last_voice_time
            )

            if silence_duration >= self.end_silence:

                self.state = VADState.SILENCE

                self._last_voice_time = None

                self._voice_start_candidate = None

                event.speech_ended = True

        return event

    def reset(
        self,
    ) -> None:

        self.state = VADState.SILENCE
        self._voice_start_candidate = None
        self._last_voice_time = None

