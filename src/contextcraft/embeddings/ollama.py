"""Ollama embedding provider (local models).

Calls the Ollama REST API at ``http://localhost:11434`` for embedding
generation.  Useful for offline / private deployments.
"""

from __future__ import annotations

import logging

import httpx

from contextcraft.config import settings
from contextcraft.embeddings.base import BaseEmbedder
from contextcraft.http_timeouts import OLLAMA_TIMEOUT
from contextcraft.security import validate_ollama_base_url

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "nomic-embed-text"


class OllamaEmbedder(BaseEmbedder):
    """Embedding provider using a locally-running Ollama instance."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        url = validate_ollama_base_url(
            (base_url or settings.ollama_base_url),
            allow_remote=settings.ollama_allow_remote,
        )
        self._base_url = url
        self._model = model
        self._client = httpx.AsyncClient(timeout=OLLAMA_TIMEOUT)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts one-by-one (Ollama API doesn't support batching)."""
        embeddings: list[list[float]] = []
        for text in texts:
            vec = await self.embed_single(text)
            embeddings.append(vec)
        return embeddings

    async def embed_single(self, text: str) -> list[float]:
        """Embed a single text via Ollama's ``/api/embeddings`` endpoint."""
        response = await self._client.post(
            f"{self._base_url}/api/embeddings",
            json={"model": self._model, "prompt": text},
        )
        response.raise_for_status()
        data = response.json()
        return list(data["embedding"])
