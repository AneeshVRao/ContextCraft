"""Abstract base class for cross-encoder rerankers."""

from __future__ import annotations

import abc

from contextcraft.models import SearchResult


class BaseReranker(abc.ABC):
    """Abstract interface for rerankers.
    
    A reranker takes an initial set of retrieved chunks (usually from a
    fast bi-encoder or BM25 retrieval) and re-scores them using a
    more accurate cross-encoder model that evaluates the query and chunk
    together.
    """

    @abc.abstractmethod
    async def rerank(
        self, query: str, results: list[SearchResult], top_n: int
    ) -> list[SearchResult]:
        """Rerank a list of search results based on their relevance to the query.

        Parameters
        ----------
        query:
            The original user query.
        results:
            The initial retrieval results (candidate pool).
        top_n:
            The number of results to return after reranking.

        Returns
        -------
        list[SearchResult]
            The top_n results, sorted by their new relevance score.
        """
        pass
