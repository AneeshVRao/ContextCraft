"""PostgreSQL full-text search (tsvector / ts_rank).

Uses PostgreSQL's built-in ``to_tsvector`` and ``plainto_tsquery`` for
keyword-based search.  This is tf-idf rather than true BM25, but the
difference is negligible after RRF merging (Decision 3).
"""

from __future__ import annotations

import logging
from uuid import UUID

from contextcraft.db.connection import get_pool
from contextcraft.db.chunks_repo import _row_to_chunk
from contextcraft.models import CodeChunk

logger = logging.getLogger(__name__)


async def bm25_search(
    query_text: str,
    repo_id: UUID,
    top_k: int = 20,
) -> list[tuple[CodeChunk, float]]:
    """Return the top-K chunks by full-text relevance.

    Parameters
    ----------
    query_text:
        The raw search query (will be converted to a tsquery).
    repo_id:
        Scope the search to a specific repository.
    top_k:
        Number of results to return.

    Returns
    -------
    list[tuple[CodeChunk, float]]
        ``(chunk, ts_rank_score)`` pairs, highest score first.
    """
    pool = await get_pool()

    rows = await pool.fetch(
        """
        SELECT cc.*,
               ts_rank(
                   to_tsvector('english', cc.content),
                   plainto_tsquery('english', $1)
               ) AS rank_score
        FROM code_chunks cc
        WHERE cc.repo_id = $2
          AND to_tsvector('english', cc.content)
              @@ plainto_tsquery('english', $1)
        ORDER BY rank_score DESC
        LIMIT $3
        """,
        query_text,
        repo_id,
        top_k,
    )

    results = []
    for row in rows:
        chunk = _row_to_chunk(row)
        score = float(row["rank_score"])
        results.append((chunk, score))

    logger.debug("BM25 search returned %d results for '%s'", len(results), query_text)
    return results
