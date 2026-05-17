"""pgvector cosine similarity search.

Queries the ``code_chunks`` table using the ``<=>`` operator
(cosine distance) and returns the top-K most similar chunks.
"""

from __future__ import annotations

import logging
from uuid import UUID

from contextcraft.db.chunks_repo import _row_to_chunk
from contextcraft.db.connection import get_pool
from contextcraft.models import CodeChunk

logger = logging.getLogger(__name__)


async def vector_search(
    query_embedding: list[float],
    repo_id: UUID,
    top_k: int = 20,
) -> list[tuple[CodeChunk, float]]:
    """Return the top-K chunks by cosine similarity to *query_embedding*.

    Parameters
    ----------
    query_embedding:
        The query text's embedding vector (1536-d for text-embedding-3-small).
    repo_id:
        Scope the search to a specific repository.
    top_k:
        Number of results to return.

    Returns
    -------
    list[tuple[CodeChunk, float]]
        ``(chunk, cosine_distance)`` pairs, lowest distance first.
    """
    pool = await get_pool()

    # pgvector expects a string representation like '[0.1, 0.2, ...]'
    vec_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    rows = await pool.fetch(
        """
        SELECT cc.*,
               (embedding <=> $1::vector) AS distance
        FROM code_chunks cc
        WHERE cc.repo_id = $2
          AND cc.embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT $3
        """,
        vec_str,
        repo_id,
        top_k,
    )

    results = []
    for row in rows:
        chunk = _row_to_chunk(row)
        distance = float(row["distance"])
        results.append((chunk, distance))

    logger.debug("Vector search returned %d results", len(results))
    return results
