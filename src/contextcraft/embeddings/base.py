"""Abstract base class for embedding providers.

All embedders implement the same async interface so the rest of the
codebase can swap providers via a single config change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseEmbedder(ABC):
    """Interface that every embedding provider must implement."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts and return their vector representations.

        Parameters
        ----------
        texts:
            Strings to embed.  The implementation handles batching and
            rate-limit retries internally.

        Returns
        -------
        list[list[float]]
            One embedding vector per input text, in the same order.
        """
        ...

    @abstractmethod
    async def embed_single(self, text: str) -> list[float]:
        """Embed a single text string.  Convenience wrapper."""
        ...
