"""Cohere reranker implementation."""

from __future__ import annotations

import logging

import cohere

from contextcraft.config import settings
from contextcraft.models import SearchResult
from contextcraft.reranker.base import BaseReranker

logger = logging.getLogger(__name__)


class CohereReranker(BaseReranker):
    """Reranker using Cohere's API.
    
    Requires CONTEXTCRAFT_COHERE_API_KEY to be set.
    """

    def __init__(self) -> None:
        if not settings.cohere_api_key:
            raise ValueError(
                "CONTEXTCRAFT_COHERE_API_KEY must be set to use CohereReranker"
            )
        self.client = cohere.AsyncClient(api_key=settings.cohere_api_key)
        self.model = settings.rerank_model

    async def rerank(
        self, query: str, results: list[SearchResult], top_n: int
    ) -> list[SearchResult]:
        if not results:
            return []

        # If we have fewer results than top_n, just return them
        # (Cohere still scores them, but no filtering is strictly needed,
        # though we might still want to sort by the new scores).

        # Extract text documents for the reranker
        documents = [res.chunk.content for res in results]

        try:
            logger.debug(
                "Calling Cohere rerank model='%s' with %d documents for top_n=%d",
                self.model,
                len(documents),
                top_n,
            )
            response = await self.client.rerank(
                model=self.model,
                query=query,
                documents=documents,
                top_n=top_n,
                return_documents=False,
            )

            reranked_results: list[SearchResult] = []
            for rank_idx, r in enumerate(response.results, start=1):
                # r.index maps back to the index in the original `documents` list
                orig_result = results[r.index]

                # Create a new SearchResult with the updated score and rank
                reranked_results.append(
                    SearchResult(
                        chunk=orig_result.chunk,
                        score=r.relevance_score,
                        rank=rank_idx,
                    )
                )

            logger.info("Cohere reranked %d candidates down to %d", len(results), len(reranked_results))
            return reranked_results

        except Exception as e:
            logger.error("Cohere reranker failed: %s", e)
            # Fallback to the original ranking
            logger.warning("Falling back to original RRF ranking due to reranker error.")
            return results[:top_n]
