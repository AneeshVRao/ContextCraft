"""OpenAI LLM provider."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

if TYPE_CHECKING:
    from openai import AsyncStream
    from openai.types.chat import ChatCompletionChunk

from contextcraft.config import settings
from contextcraft.llm.base import BaseLLM

logger = logging.getLogger(__name__)


class OpenAILLM(BaseLLM):
    """OpenAI chat completion provider."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
        self._model = model or settings.openai_chat_model
        self._stream: AsyncStream[ChatCompletionChunk] | None = None

    async def close(self) -> None:
        if self._stream is not None:
            await self._stream.close()
            self._stream = None

    async def generate(self, system_prompt: str, user_message: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.1,
        )
        return response.choices[0].message.content or ""

    async def stream(self, system_prompt: str, user_message: str) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.1,
            stream=True,
        )
        self._stream = stream
        try:
            async for event in stream:
                delta = event.choices[0].delta
                if delta.content:
                    yield delta.content
        except asyncio.CancelledError:
            await self.close()
            raise
        finally:
            self._stream = None
