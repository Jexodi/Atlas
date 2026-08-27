import asyncio

from atlas.audio.pipeline import AudioPipeline
from atlas.audio.output import AudioOutput
from atlas.audio.echo_guard import EchoGuard

from atlas.audio.capture import (
    MicrophoneCapture,
)

from atlas.audio.devices import (
    AudioDeviceManager,
)

from atlas.audio.vad import (
    VoiceActivityDetector,
)

from atlas.audio.mode import ListeningMode

from atlas.audio.wakeword import (
    create_wake_word_detector,
)

from atlas.core.event_bus import EventBus


class AudioManager:

    def __init__(
        self,
        event_bus: EventBus,
        logger,
    ) -> None:

        self.event_bus = event_bus
        self.logger = logger

        self.devices = AudioDeviceManager()

        self.microphone: (
            MicrophoneCapture | None
        ) = None

        self.vad: (
            VoiceActivityDetector | None
        ) = None

        self.current_level_db = -100.0

        self.speech_active = False

        self.pipeline: (
            AudioPipeline | None
        ) = None

        self._event_loop: (
            asyncio.AbstractEventLoop | None
        ) = None

        self.echo_guard = EchoGuard(
            sample_rate=24000,
        )

        self.output = AudioOutput(
            logger=self.logger,
            sample_rate=24000,
            channels=1,
            echo_guard=self.echo_guard,
        )

    def initialize(
        self,
        config,
    ) -> None:

        default_input = (
            self.devices.get_default_input()
        )

        if default_input is None:

            self.logger.warning(
                "Aucun microphone par défaut détecté."
            )

            return


        sample_rate = config.get(
            "audio.sample_rate",
            24000,
        )

        channels = config.get(
            "audio.channels",
            1,
        )


        self.logger.info(
            "Microphone détecté : %s",
            default_input.name,
        )


        self.microphone = MicrophoneCapture(
            logger=self.logger,
            device_index=default_input.index,
            sample_rate=sample_rate,
            channels=channels,
        )


        self.microphone.set_chunk_callback(
            self._on_audio_chunk
        )

        vad_enabled = config.get(
            "audio.vad.enabled",
            True,
        )

        if vad_enabled:

            self.vad = VoiceActivityDetector(
                threshold_db=config.get(
                    "audio.vad.threshold_db",
                    -35.0,
                ),

                start_duration_ms=config.get(
                    "audio.vad.start_duration_ms",
                    120,
                ),

                end_silence_ms=config.get(
                    "audio.vad.end_silence_ms",
                    700,
                ),
            )

            self.logger.info(
                "VAD local initialisé."
            )

        wake_word_detector = (
            create_wake_word_detector(
                config=config,
                logger=self.logger,
            )
        )

        configured_mode = config.get(
            "audio.listening_mode",
            None,
        )

        if configured_mode is None:
            configured_mode = (
                "continuous"
                if config.get(
                    "audio.continuous_listening",
                    False,
                )
                else "wake_word"
            )

        try:
            listening_mode = ListeningMode.from_value(
                configured_mode
            )
        except ValueError:
            self.logger.warning(
                "Mode d'écoute '%s' invalide. "
                "Utilisation de continuous.",
                configured_mode,
            )
            listening_mode = ListeningMode.CONTINUOUS

        if (
            listening_mode
            == ListeningMode.WAKE_WORD
            and wake_word_detector is None
        ):
            self.logger.warning(
                "Mode wake_word demande mais Windows Speech "
                "n'est pas disponible. Retour en ecoute continue."
            )
            listening_mode = ListeningMode.CONTINUOUS

        self.pipeline = AudioPipeline(
            event_bus=self.event_bus,
            logger=self.logger,
            vad=self.vad,
            wake_word_detector=(
                wake_word_detector
            ),
            echo_guard=self.echo_guard,
            listening_mode=listening_mode,
            pre_roll_ms=config.get(
                "audio.pre_roll_ms",
                500,
            ),
            sample_rate=sample_rate,
            block_size=960,
        )

    @property
    def listening_mode(
        self,
    ) -> ListeningMode | None:

        if self.pipeline is None:
            return None

        return self.pipeline.listening_mode

    def set_listening_mode(
        self,
        mode: ListeningMode | str,
    ) -> ListeningMode:

        if self.pipeline is None:
            raise RuntimeError(
                "Le pipeline audio Atlas n'est pas initialisé."
            )

        requested_mode = ListeningMode.from_value(
            mode
        )

        if (
            requested_mode
            == ListeningMode.WAKE_WORD
            and self.pipeline.wake_word_detector
            is None
        ):
            raise RuntimeError(
                "Le moteur Windows Speech du wake word "
                "n'est pas disponible."
            )

        return self.pipeline.set_listening_mode(
            requested_mode
        )

    def set_event_loop(
        self,
        loop: asyncio.AbstractEventLoop,
    ) -> None:

        self._event_loop = loop

    def _on_audio_chunk(
        self,
        chunk,
    ) -> None:

        if self.pipeline is None:
            return

        if self._event_loop is None:
            return

        self._event_loop.call_soon_threadsafe(
            self._enqueue_chunk,
            chunk,
        )

    def _enqueue_chunk(
        self,
        chunk,
    ) -> None:

        if self.pipeline is None:
            return

        try:

            self.pipeline.queue.put_nowait(
                chunk
            )

        except asyncio.QueueFull:

            self.logger.warning(
                "AudioQueue pleine : bloc audio ignoré."
            )



