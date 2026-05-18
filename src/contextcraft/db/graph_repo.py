"""CRUD operations for the chunk_edges table."""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg

from contextcraft.db.connection import get_pool
from contextcraft.graph.models import ChunkEdge

logger = logging.getLogger(__name__)


async def run_graph_migration() -> None:
    """Run the chunk_edges migration."""
    pool = await get_pool()
    migration_sql = """
    CREATE TABLE IF NOT EXISTS chunk_edges (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        source_chunk_id UUID NOT NULL REFERENCES code_chunks(id) ON DELETE CASCADE,
        target_chunk_id UUID NOT NULL REFERENCES code_chunks(id) ON DELETE CASCADE,
        edge_type       TEXT NOT NULL,
        confidence      FLOAT NOT NULL DEFAULT 1.0,
        UNIQUE(source_chunk_id, target_chunk_id, edge_type)
    );
    CREATE INDEX IF NOT EXISTS idx_edges_source ON chunk_edges(source_chunk_id);
    CREATE INDEX IF NOT EXISTS idx_edges_target ON chunk_edges(target_chunk_id);
    """
    await pool.execute(migration_sql)
    logger.info("chunk_edges migration applied")


async def insert_edges(edges: list[ChunkEdge]) -> int:
    """Bulk-insert dependency edges. Returns inserted count.

    Uses ON CONFLICT to skip duplicates.
    """
    if not edges:
        return 0

    pool = await get_pool()
    records = [
        (
            edge.source_chunk_id,
            edge.target_chunk_id,
            edge.edge_type,
            edge.confidence,
        )
        for edge in edges
    ]

    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO chunk_edges (source_chunk_id, target_chunk_id, edge_type, confidence)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (source_chunk_id, target_chunk_id, edge_type) DO UPDATE
                SET confidence = EXCLUDED.confidence
            """,
            records,
        )

    logger.info("Inserted %d edges", len(records))
    return len(records)


async def get_dependencies(
    chunk_ids: list[UUID],
    edge_types: tuple[str, ...] = ("imports", "inherits"),
    min_confidence: float = 0.7,
    limit: int = 10,
) -> list[asyncpg.Record]:
    """Fetch 1-hop dependency chunks in a single batched query.

    Returns raw rows from code_chunks — caller converts to CodeChunk.
    Skips chunks already in chunk_ids. Caps at ``limit`` results.

    Cycle detection for graph expansion lives in ``graph.expander``
    (``visited`` set).  A recursive SQL CTE with ``NOT target = ANY(visited)``
    is available if multi-hop expansion is added later.
    """
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT DISTINCT c.*
        FROM code_chunks c
        JOIN chunk_edges e ON c.id = e.target_chunk_id
        WHERE e.source_chunk_id = ANY($1::uuid[])
          AND e.edge_type = ANY($2::text[])
          AND e.confidence >= $3
          AND c.id != ALL($1::uuid[])
        LIMIT $4
        """,
        chunk_ids,
        list(edge_types),
        min_confidence,
        limit,
    )
    return list(rows)


async def delete_edges_by_repo(repo_id: UUID) -> int:
    """Delete all edges whose source chunk belongs to the given repo."""
    pool = await get_pool()
    result = await pool.execute(
        """
        DELETE FROM chunk_edges
        WHERE source_chunk_id IN (
            SELECT id FROM code_chunks WHERE repo_id = $1
        )
        """,
        repo_id,
    )
    count = int(result.split()[-1])
    logger.info("Deleted %d edges for repo %s", count, repo_id)
    return count


async def get_edge_count(repo_id: UUID) -> int:
    """Count edges for chunks belonging to a given repo."""
    pool = await get_pool()
    count = await pool.fetchval(
        """
        SELECT COUNT(*) FROM chunk_edges
        WHERE source_chunk_id IN (
            SELECT id FROM code_chunks WHERE repo_id = $1
        )
        """,
        repo_id,
    )
    return int(count)
