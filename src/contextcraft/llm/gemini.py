"""Gemini LLM provider.

Uses the official google-genai library to call Google's Gemini models.
Supports streaming and non-streaming generation.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

from contextcraft.config import settings
from contextcraft.llm.base import BaseLLM

logger = logging.getLogger(__name__)


class GeminiLLM(BaseLLM):
    """Google Gemini LLM provider."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.gemini_api_key
        if not self.api_key:
            raise ValueError(
                "CONTEXTCRAFT_GEMINI_API_KEY environment variable is missing. "
                "Get a free API key at https://aistudio.google.com/app/apikey"
            )
        self.client = genai.Client(api_key=self.api_key)
        self.model = model or settings.gemini_chat_model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def generate(self, system_prompt: str, user_message: str) -> str:
        """Generate a complete response (non-streaming)."""
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.1,
            ),
        )
        return str(response.text)

    async def stream(self, system_prompt: str, user_message: str) -> AsyncIterator[str]:
        """Yield response tokens as they arrive."""
        response = await self.client.aio.models.generate_content_stream(
            model=self.model,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.1,
            ),
        )
        async for chunk in response:
            if chunk.text:
                yield chunk.text
