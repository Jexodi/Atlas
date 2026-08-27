import os

from openai import AsyncOpenAI

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

        api_key = os.getenv(
            "OPENAI_API_KEY"
        )

        if not api_key:

            raise RuntimeError(
                "OPENAI_API_KEY absente du fichier .env."
            )

        self.transcription_model = config.get(
            "openai.transcription_model",
            "gpt-transcribe",
        )

        self.client = AsyncOpenAI(
            api_key=api_key
        )

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