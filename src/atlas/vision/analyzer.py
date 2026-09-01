from __future__ import annotations

import asyncio
import base64
from pathlib import Path

from atlas.ai.access import create_client


class VisionAnalysisError(RuntimeError):
    pass


class VisionAnalyzer:
    def __init__(self, *, model: str, logger) -> None:
        self.model = str(model or "gpt-5.6-luna")
        self.logger = logger

    def analyze_image(self, image_path: str | Path, prompt: str) -> str:
        return asyncio.run(self._analyze_image_async(Path(image_path), prompt))

    async def _analyze_image_async(self, image_path: Path, prompt: str) -> str:
        if not image_path.is_file():
            raise VisionAnalysisError("La capture à analyser est introuvable.")

        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        data_url = f"data:image/png;base64,{encoded}"
        client = create_client()
        try:
            response = await client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": prompt,
                            },
                            {
                                "type": "input_image",
                                "image_url": data_url,
                            },
                        ],
                    }
                ],
            )
            text = (getattr(response, "output_text", None) or "").strip()
            if not text:
                raise VisionAnalysisError("OpenAI n'a renvoyé aucune analyse visuelle exploitable.")
            return text
        finally:
            await client.close()
