from openai import AsyncOpenAI
from atlas.ai.access import create_client

from atlas.ai.audio import (
    utterance_to_wav,
)


class OpenAIManager:

    def __init__(
        self,
        logger,
    ) -> None:

        self.logger = logger

        self.client: (
            AsyncOpenAI | None
        ) = None

        self.transcription_model = (
            "gpt-transcribe"
        )

    def initialize(
        self,
        config,
    ) -> None:

        self.transcription_model = config.get(
            "openai.transcription_model",
            "gpt-transcribe",
        )

        self.client = create_client()

        self.logger.info(
            "Client OpenAI initialisé."
        )

    async def transcribe(
        self,
        utterance,
    ) -> str:

        if self.client is None:

            raise RuntimeError(
                "OpenAIManager non initialisé."
            )

        wav_file = utterance_to_wav(
            utterance
        )

        self.logger.debug(
            "Envoi de %.2f s d'audio à OpenAI.",
            utterance.duration_seconds,
        )

        response = (
            await self.client.audio.transcriptions.create(
                model=self.transcription_model,
                file=wav_file,
                language="fr",
            )
        )

        text = response.text.strip()

        return text
