"""Context expander — enriches retrieved chunks with 1-hop dependencies.

After hybrid search retrieves the top-k chunks, the expander queries
``chunk_edges`` to find imports and inherited bases, pulling in the
definitions that the retrieved code depends on.

Design constraints (per user review):
- Single batched SQL query (not N round-trips)
- LIMIT 10 to prevent context window bloat from highly connected nodes
- Cycle guard via visited set (safe for future 2-hop expansion)
- Filters by min_confidence to exclude uncertain edges
"""

from __future__ import annotations

import logging
from uuid import UUID

from contextcraft.db.chunks_repo import _row_to_chunk
from contextcraft.db.graph_repo import get_dependencies
from contextcraft.models import CodeChunk

logger = logging.getLogger(__name__)


async def expand_with_deps(
    chunk_ids: list[UUID],
    edge_types: tuple[str, ...] = ("imports", "inherits"),
    min_confidence: float = 0.7,
    limit: int = 10,
    visited: set[UUID] | None = None,
) -> list[CodeChunk]:
    """Fetch 1-hop dependency chunks with cycle detection.

    Parameters
    ----------
    chunk_ids:
        IDs of the initially retrieved chunks.
    edge_types:
        Which edge types to follow (default: imports + inherits).
    min_confidence:
        Minimum edge confidence to include (default: 0.7).
        This filters out uncertain __init__ re-exports (0.5) by default.
    limit:
        Maximum number of dependency chunks to return.
    visited:
        Set of already-seen chunk IDs to prevent cycles.
        Automatically initialised from ``chunk_ids`` if None.

    Returns
    -------
    list[CodeChunk]
        Dependency chunks not already in the retrieved set.
    """
    visited = visited if visited is not None else set(chunk_ids)

    rows = await get_dependencies(
        chunk_ids=chunk_ids,
        edge_types=edge_types,
        min_confidence=min_confidence,
        limit=limit,
    )

    # Convert rows and filter out anything already visited
    dep_chunks: list[CodeChunk] = []
    for row in rows:
        chunk = _row_to_chunk(row)
        if chunk.id not in visited:
            visited.add(chunk.id)
            dep_chunks.append(chunk)

    if dep_chunks:
        logger.info(
            "Expanded context with %d dependency chunks (from %d source chunks)",
            len(dep_chunks),
            len(chunk_ids),
        )

    return dep_chunks
