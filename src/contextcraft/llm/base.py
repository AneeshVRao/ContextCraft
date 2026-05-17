"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class BaseLLM(ABC):
    """Interface that every LLM provider must implement."""

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_message: str,
    ) -> str:
        """Generate a complete response (non-streaming)."""
        ...

    @abstractmethod
    def stream(
        self,
        system_prompt: str,
        user_message: str,
    ) -> AsyncIterator[str]:
        """Yield response tokens as they arrive."""
        ...
