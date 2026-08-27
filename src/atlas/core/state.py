from dataclasses import dataclass


@dataclass
class AtlasState:

    running: bool = False

    status: str = "starting"

    mode: str = "normal"

    openai_connected: bool = False

    atlas_service_connected: bool = False

    microphone_active: bool = False

    audio_level_db: float = -100.0

    wake_word_detected: bool = False

    voice_session_active: bool = False

    speech_active: bool = False

    listening: bool = False

    speaking: bool = False

    active_window: str | None = None