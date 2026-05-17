"""OpenAI embedding provider.

Uses ``text-embedding-3-small`` by default.  Batches requests in groups
of ``embedding_batch_size`` and retries on 429 / 5xx with tenacity.
"""

from __future__ import annotations

import asyncio
import logging

from openai import AsyncOpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from contextcraft.config import settings
from contextcraft.embeddings.base import BaseEmbedder

logger = logging.getLogger(__name__)


class OpenAIEmbedder(BaseEmbedder):
    """Async OpenAI embedding client with batching and retry."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        batch_size: int | None = None,
        max_concurrent: int | None = None,
    ):
        self._client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
        self._model = model or settings.embedding_model
        self._batch_size = batch_size or settings.embedding_batch_size
        self._semaphore = asyncio.Semaphore(max_concurrent or settings.embedding_max_concurrent)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in batches, respecting concurrency limits."""
        if not texts:
            return []

        batches = [texts[i : i + self._batch_size] for i in range(0, len(texts), self._batch_size)]

        all_embeddings: list[list[float]] = []
        for batch in batches:
            result = await self._embed_batch(batch)
            all_embeddings.extend(result)

        return all_embeddings

    async def embed_single(self, text: str) -> list[float]:
        """Embed a single text string."""
        results = await self.embed([text])
        return results[0]

    @retry(
        retry=retry_if_exception_type((Exception,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Send one batch to the OpenAI API with rate-limit protection."""
        async with self._semaphore:
            logger.debug("Embedding batch of %d texts", len(texts))
            response = await self._client.embeddings.create(
                input=texts,
                model=self._model,
            )
            # Sort by index to guarantee order matches input
            sorted_data = sorted(response.data, key=lambda d: d.index)
            return [d.embedding for d in sorted_data]
