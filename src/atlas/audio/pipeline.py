import asyncio
import math
from collections import deque

import numpy as np

from atlas.audio.chunks import AudioChunk
from atlas.audio.mode import ListeningMode
from atlas.audio.vad import VoiceActivityDetector
from atlas.audio.wakeword import WakeWordDetector
from atlas.core.event_bus import EventBus

from atlas.audio.utterance import (
    UtteranceBuffer,
)


class AudioPipeline:

    def __init__(
        self,
        event_bus: EventBus,
        logger,
        vad: VoiceActivityDetector | None = None,
        wake_word_detector: WakeWordDetector | None = None,
        echo_guard=None,
        continuous_listening: bool = False,
        listening_mode: ListeningMode | str | None = None,
        pre_roll_ms: int = 500,
        sample_rate: int = 24000,
        block_size: int = 960,
    ) -> None:

        self.event_bus = event_bus
        self.logger = logger
        self.vad = vad
        self.wake_word_detector = wake_word_detector
        self.echo_guard = echo_guard

        if listening_mode is None:
            listening_mode = (
                ListeningMode.CONTINUOUS
                if continuous_listening
                else ListeningMode.WAKE_WORD
            )

        self.listening_mode = ListeningMode.from_value(
            listening_mode
        )

        self.sample_rate = sample_rate
        self.block_size = block_size

        self.queue: asyncio.Queue[AudioChunk] = asyncio.Queue(
            maxsize=100
        )

        self.realtime_queue: asyncio.Queue[
            AudioChunk | None
        ] = asyncio.Queue(
            maxsize=100
        )

        block_duration_ms = (
            block_size / sample_rate
        ) * 1000

        pre_roll_blocks = max(
            1,
            round(
                pre_roll_ms / block_duration_ms
            ),
        )

        self.pre_roll = deque(
            maxlen=pre_roll_blocks
        )

        self.utterance_buffer = UtteranceBuffer()
        self.speech_active = False
        self.current_level_db = -100.0

        self.voice_session_active = (
            self.listening_mode
            == ListeningMode.CONTINUOUS
        )

    @property
    def continuous_listening(
        self,
    ) -> bool:

        return (
            self.listening_mode
            == ListeningMode.CONTINUOUS
        )

    def calculate_level(
        self,
        samples: np.ndarray,
    ) -> float:

        rms = float(
            np.sqrt(
                np.mean(
                    np.square(samples)
                )
            )
        )

        if rms <= 0:
            return -100.0

        return 20.0 * math.log10(rms)

    async def run(self) -> None:

        self.logger.info(
            "Pipeline audio démarré (mode=%s).",
            self.listening_mode.value,
        )

        try:
            while True:

                chunk = await self.queue.get()

                try:
                    self.process_chunk(
                        chunk
                    )
                finally:
                    self.queue.task_done()

        except asyncio.CancelledError:

            self.logger.info(
                "Pipeline audio arrêté."
            )

            raise

    def process_chunk(
        self,
        chunk: AudioChunk,
    ) -> None:

        self.pre_roll.append(
            chunk
        )

        level_db = self.calculate_level(
            chunk.samples
        )

        self.current_level_db = level_db

        self.event_bus.publish(
            "audio.level",
            {
                "level_db": level_db,
            },
        )

        # En mode wake word, tout s'arrête ici tant qu'Sideron
        # n'a pas été réveillé. Aucun VAD, aucun realtime_queue.
        if (
            self.listening_mode
            == ListeningMode.WAKE_WORD
            and not self.voice_session_active
        ):

            if self.wake_word_detector is None:
                return

            detected = self.wake_word_detector.process(
                chunk.samples,
                chunk.sample_rate,
            )

            if not detected:
                return

            self.voice_session_active = True

            self.logger.info(
                "Wake word Sideron détecté : session vocale ouverte."
            )

            self.event_bus.publish(
                "audio.wake_word_detected"
            )

        if self.utterance_buffer.recording:

            self.utterance_buffer.add(
                chunk
            )

            try:
                self.realtime_queue.put_nowait(
                    chunk
                )
            except asyncio.QueueFull:
                self.logger.warning(
                    "Realtime AudioQueue pleine : bloc ignoré."
                )

        if self.vad is None:
            return

        if (
            self.echo_guard is not None
            and self.echo_guard.is_likely_echo(
                chunk.samples
            )
        ):
            self.logger.debug(
                "Écho Sideron détecté : bloc ignoré par le VAD."
            )
            return

        event = self.vad.process(
            level_db
        )

        if event.speech_started:

            self.speech_active = True

            self.utterance_buffer.start(
                pre_roll=list(
                    self.pre_roll
                )
            )

            for pre_roll_chunk in list(
                self.pre_roll
            ):
                try:
                    self.realtime_queue.put_nowait(
                        pre_roll_chunk
                    )
                except asyncio.QueueFull:
                    self.logger.warning(
                        "Realtime AudioQueue pleine : pre-roll ignoré."
                    )
                    break

            self.logger.debug(
                "Début de parole détecté."
            )

            self.event_bus.publish(
                "audio.speech_started"
            )

        if event.speech_ended:

            self.speech_active = False

            utterance = (
                self.utterance_buffer.finish()
            )

            self.logger.debug(
                "Fin de parole détectée."
            )

            self.event_bus.publish(
                "audio.speech_ended"
            )

            if utterance is not None:
                self.event_bus.publish(
                    "audio.utterance_ready",
                    utterance,
                )

            try:
                self.realtime_queue.put_nowait(
                    None
                )
            except asyncio.QueueFull:
                self.logger.warning(
                    "Impossible de signaler la fin de parole à Realtime."
                )

    def set_listening_mode(
        self,
        mode: ListeningMode | str,
    ) -> ListeningMode:

        new_mode = ListeningMode.from_value(
            mode
        )

        if new_mode == self.listening_mode:
            return new_mode

        previous_mode = self.listening_mode
        self.listening_mode = new_mode

        self._reset_capture_state()

        self.voice_session_active = (
            new_mode
            == ListeningMode.CONTINUOUS
        )

        self.logger.info(
            "Mode d'écoute Sideron : %s -> %s.",
            previous_mode.value,
            new_mode.value,
        )

        self.event_bus.publish(
            "audio.listening_mode_changed",
            {
                "mode": new_mode.value,
                "previous_mode": previous_mode.value,
                "voice_session_active": (
                    self.voice_session_active
                ),
            },
        )

        if new_mode == ListeningMode.WAKE_WORD:
            self.event_bus.publish(
                "audio.voice_session_closed"
            )

        return new_mode

    def close_voice_session(
        self,
    ) -> None:

        if (
            self.listening_mode
            == ListeningMode.CONTINUOUS
        ):
            return

        if not self.voice_session_active:
            return

        self.voice_session_active = False
        self._reset_capture_state()

        self.event_bus.publish(
            "audio.voice_session_closed"
        )

    def _reset_capture_state(
        self,
    ) -> None:

        self.speech_active = False
        self.pre_roll.clear()
        self.utterance_buffer = UtteranceBuffer()

        if self.vad is not None:
            self.vad.reset()

        if self.wake_word_detector is not None:
            self.wake_word_detector.reset()
