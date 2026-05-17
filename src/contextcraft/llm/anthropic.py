"""Anthropic (Claude) LLM provider."""

from __future__ import annotations

import logging
from typing import AsyncIterator

from anthropic import AsyncAnthropic

from contextcraft.config import settings
from contextcraft.llm.base import BaseLLM

logger = logging.getLogger(__name__)


class AnthropicLLM(BaseLLM):
    """Anthropic Claude chat completion provider."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self._client = AsyncAnthropic(api_key=api_key or settings.anthropic_api_key)
        self._model = model or settings.anthropic_model

    async def generate(self, system_prompt: str, user_message: str) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            temperature=0.1,
        )
        return response.content[0].text

    async def stream(
        self, system_prompt: str, user_message: str
    ) -> AsyncIterator[str]:
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            temperature=0.1,
        ) as stream:
            async for text in stream.text_stream:
                yield text
