"""Reciprocal Rank Fusion (RRF) hybrid search.

Combines vector search and BM25 full-text search results using RRF:
    score = Σ  1 / (k + rank)
where k = 60 (standard RRF constant).

Can also execute the fused query entirely in SQL for maximum efficiency.
"""

from __future__ import annotations

import logging
from uuid import UUID

from contextcraft.db.chunks_repo import _row_to_chunk
from contextcraft.db.connection import get_pool
from contextcraft.models import SearchResult

logger = logging.getLogger(__name__)

RRF_K = 60  # Standard RRF constant


async def hybrid_search(
    query_embedding: list[float],
    query_text: str,
    repo_id: UUID,
    top_k: int = 10,
) -> list[SearchResult]:
    """Run hybrid vector + BM25 search with RRF fusion.

    Executes the full RRF query in a single SQL statement for efficiency:
    both the vector ranking and the BM25 ranking are computed in CTEs,
    then fused with RRF scoring.

    Parameters
    ----------
    query_embedding:
        Embedding vector for the query.
    query_text:
        Raw query text for full-text search.
    repo_id:
        Scope to a specific repository.
    top_k:
        Number of final results to return.

    Returns
    -------
    list[SearchResult]
        Ranked chunks with RRF scores.
    """
    pool = await get_pool()
    vec_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    rows = await pool.fetch(
        """
        WITH vector_results AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       ORDER BY embedding <=> $1::vector
                   ) AS rank
            FROM code_chunks
            WHERE repo_id = $2
              AND embedding IS NOT NULL
            ORDER BY embedding <=> $1::vector
            LIMIT 60
        ),
        bm25_results AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       ORDER BY ts_rank(
                           to_tsvector('english', content),
                           plainto_tsquery('english', $3)
                       ) DESC
                   ) AS rank
            FROM code_chunks
            WHERE repo_id = $2
              AND to_tsvector('english', content)
                  @@ plainto_tsquery('english', $3)
            LIMIT 60
        ),
        rrf AS (
            SELECT COALESCE(v.id, b.id) AS id,
                   COALESCE(1.0 / (60 + v.rank), 0)
                   + COALESCE(1.0 / (60 + b.rank), 0) AS rrf_score
            FROM vector_results v
            FULL OUTER JOIN bm25_results b ON v.id = b.id
        )
        SELECT cc.*, r.rrf_score
        FROM rrf r
        JOIN code_chunks cc ON cc.id = r.id
        ORDER BY r.rrf_score DESC, cc.id ASC
        LIMIT $4
        """,
        vec_str,
        repo_id,
        query_text,
        top_k,
    )

    results: list[SearchResult] = []
    for rank_idx, row in enumerate(rows, start=1):
        chunk = _row_to_chunk(row)
        results.append(
            SearchResult(
                chunk=chunk,
                score=float(row["rrf_score"]),
                rank=rank_idx,
            )
        )

    logger.info(
        "Hybrid search returned %d results (query: '%s…')",
        len(results),
        query_text[:50],
    )
    return results
