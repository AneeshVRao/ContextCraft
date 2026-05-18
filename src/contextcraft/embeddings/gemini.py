"""Gemini Embedder.

Uses the official google-genai library to generate embeddings.
Default model is `text-embedding-004`.
"""

from __future__ import annotations

import asyncio
import logging

from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

from contextcraft.config import settings
from contextcraft.embeddings.base import BaseEmbedder

logger = logging.getLogger(__name__)


class GeminiEmbedder(BaseEmbedder):
    """Google Gemini embedding provider."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.gemini_api_key
        if not self.api_key:
            raise ValueError(
                "CONTEXTCRAFT_GEMINI_API_KEY environment variable is missing. "
                "Get a free API key at https://aistudio.google.com/app/apikey"
            )
        self.client = genai.Client(api_key=self.api_key)
        self.model = model or settings.embedding_model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts using Gemini."""
        if not texts:
            return []

        sem = asyncio.Semaphore(settings.embedding_max_concurrent)

        async def embed_single_text(text: str) -> list[float]:
            if not text.strip():
                return [0.0] * 1536
            async with sem:
                # Sleep to respect 100 Requests Per Minute (RPM) free tier quota limit
                await asyncio.sleep(3.0)
                res = await self.client.aio.models.embed_content(
                    model=self.model,
                    contents=text,
                    config=types.EmbedContentConfig(output_dimensionality=1536),
                )
                assert res.embeddings is not None
                assert res.embeddings[0].values is not None
                return list(res.embeddings[0].values)

        tasks = [embed_single_text(text) for text in texts]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def embed_single(self, text: str) -> list[float]:
        """Embed a single text string."""
        vectors = await self.embed([text])
        return vectors[0]
