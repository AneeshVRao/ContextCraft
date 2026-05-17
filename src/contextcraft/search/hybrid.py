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


async def _search_one_repo(
    query_embedding: list[float],
    query_text: str,
    repo_id: UUID,
    top_k: int = 10,
) -> list[SearchResult]:
    """Execute the full RRF query in a single SQL statement for one repo."""
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
    return results


async def hybrid_search(
    query_embedding: list[float],
    query_text: str,
    repo_ids: list[UUID],
    top_k: int = 10,
) -> list[SearchResult]:
    """Run hybrid vector + BM25 search with per-repo RRF fusion.

    Computes RRF scores independently within each repo to prevent large repos
    from dominating the rank positions, then merges the per-repo top-K lists.

    Parameters
    ----------
    query_embedding:
        Embedding vector for the query.
    query_text:
        Raw query text for full-text search.
    repo_ids:
        List of repositories to search across.
    top_k:
        Number of final results to return.

    Returns
    -------
    list[SearchResult]
        Ranked chunks merged across repos.
    """
    if not repo_ids:
        return []

    # Fetch RRF-ranked results for each repo independently
    all_results: list[SearchResult] = []
    for repo_id in repo_ids:
        repo_results = await _search_one_repo(
            query_embedding=query_embedding,
            query_text=query_text,
            repo_id=repo_id,
            top_k=top_k,  # fetch full top_k per repo so we have enough candidates
        )
        all_results.extend(repo_results)

    # Sort merged results by RRF score descending
    all_results.sort(key=lambda sr: sr.score, reverse=True)

    # Take global top K and reassign ranks
    final_results = all_results[:top_k]
    for i, sr in enumerate(final_results, start=1):
        sr.rank = i

    logger.info(
        "Hybrid search returned %d cross-repo results (query: '%s…')",
        len(final_results),
        query_text[:50],
    )
    return final_results
