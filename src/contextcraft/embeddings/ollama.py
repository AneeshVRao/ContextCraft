"""Ollama embedding provider (local models).

Calls the Ollama REST API at ``http://localhost:11434`` for embedding
generation.  Useful for offline / private deployments.
"""

from __future__ import annotations

import logging

import httpx

from contextcraft.embeddings.base import BaseEmbedder

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "nomic-embed-text"


class OllamaEmbedder(BaseEmbedder):
    """Embedding provider using a locally-running Ollama instance."""

    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_URL,
        model: str = DEFAULT_MODEL,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=120.0)

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
