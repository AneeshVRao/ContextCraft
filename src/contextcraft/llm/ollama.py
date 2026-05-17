"""Ollama local LLM provider.

Uses httpx to call the Ollama REST API at ``http://localhost:11434``.
Supports both ``generate()`` and ``stream()`` via ``/api/chat``.

Default model: ``qwen2.5-coder:7b`` — best-in-class for code tasks
at 5 GB RAM. Override with ``CONTEXTCRAFT_OLLAMA_MODEL``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx

from contextcraft.config import settings
from contextcraft.llm.base import BaseLLM

logger = logging.getLogger(__name__)


class OllamaConnectionError(RuntimeError):
    """Raised when Ollama is not reachable."""


class OllamaLLM(BaseLLM):
    """Ollama local LLM provider.

    Communicates with the Ollama server via HTTP. On first use, verifies
    that the server is running and the model is available.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.ollama_model
        self._verified = False

    async def _verify_connection(self) -> None:
        """Check that Ollama is running and the model is available.

        Hits ``/api/tags`` and raises ``OllamaConnectionError`` with a
        clear message if the server is unreachable.
        """
        if self._verified:
            return

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                resp.raise_for_status()
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise OllamaConnectionError(
                f"Ollama not running at {self._base_url}. Start it with: ollama serve"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaConnectionError(
                f"Ollama returned HTTP {exc.response.status_code}. Check your Ollama installation."
            ) from exc

        # Check if the model is available
        data = resp.json()
        available_models = [m.get("name", "") for m in data.get("models", [])]
        model_names = [m.split(":")[0] for m in available_models]
        requested_base = self._model.split(":")[0]

        if requested_base not in model_names and self._model not in available_models:
            logger.warning(
                "Model '%s' not found locally. Available: %s. "
                "Ollama will attempt to pull it on first use.",
                self._model,
                ", ".join(available_models) if available_models else "(none)",
            )

        self._verified = True
        logger.info("Ollama connection verified at %s (model: %s)", self._base_url, self._model)

    async def generate(self, system_prompt: str, user_message: str) -> str:
        """Generate a complete response (non-streaming)."""
        await self._verify_connection()

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return str(data.get("message", {}).get("content", ""))

    async def stream(self, system_prompt: str, user_message: str) -> AsyncIterator[str]:
        """Yield response tokens as they arrive from Ollama."""
        await self._verify_connection()

        async with (
            httpx.AsyncClient(timeout=120.0) as client,
            client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": True,
                    "options": {"temperature": 0.1},
                },
            ) as resp,
        ):
            resp.raise_for_status()
            import json

            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if chunk.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue
