"""CRUD operations for code_chunks and repositories.

All functions are async and operate on an ``asyncpg.Pool``.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

import asyncpg

from contextcraft.db.connection import get_pool
from contextcraft.models import (
    ChunkType,
    CodeChunk,
    CommitInfo,
    Language,
    Repository,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Repository CRUD
# ---------------------------------------------------------------------------


async def upsert_repository(
    name: str,
    local_path: str,
    languages: list[Language] | None = None,
    last_commit_hash: str | None = None,
) -> Repository:
    """Insert or update a repository record.  Returns the ``Repository``."""
    pool = await get_pool()
    lang_list = [lang.value for lang in (languages or [])]

    row = await pool.fetchrow(
        """
        INSERT INTO repositories (name, local_path, language, last_commit_hash, last_indexed_at)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (local_path) DO UPDATE
            SET name            = EXCLUDED.name,
                language        = EXCLUDED.language,
                last_commit_hash = EXCLUDED.last_commit_hash,
                last_indexed_at  = NOW()
        RETURNING *
        """,
        name,
        local_path,
        lang_list,
        last_commit_hash,
    )
    return _row_to_repository(row)


async def get_repository_by_path(local_path: str) -> Repository | None:
    """Find a repository by its local filesystem path."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM repositories WHERE local_path = $1", local_path
    )
    return _row_to_repository(row) if row else None


async def get_repository(repo_id: UUID) -> Repository | None:
    """Find a repository by ID."""
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM repositories WHERE id = $1", repo_id)
    return _row_to_repository(row) if row else None


async def list_repositories() -> list[Repository]:
    """Return all indexed repositories."""
    pool = await get_pool()
    rows = await pool.fetch("SELECT * FROM repositories ORDER BY name")
    return [_row_to_repository(r) for r in rows]


async def update_chunk_count(repo_id: UUID) -> int:
    """Recount chunks and update the repository record.  Returns the new count."""
    pool = await get_pool()
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM code_chunks WHERE repo_id = $1", repo_id
    )
    await pool.execute(
        "UPDATE repositories SET chunk_count = $1 WHERE id = $2", count, repo_id
    )
    return count


async def delete_repository(repo_id: UUID) -> None:
    """Delete a repository and all its chunks (ON DELETE CASCADE)."""
    pool = await get_pool()
    await pool.execute("DELETE FROM repositories WHERE id = $1", repo_id)


# ---------------------------------------------------------------------------
# CodeChunk CRUD
# ---------------------------------------------------------------------------


async def insert_chunks(chunks: list[CodeChunk]) -> int:
    """Bulk-insert a list of ``CodeChunk`` objects.  Returns inserted count."""
    if not chunks:
        return 0

    pool = await get_pool()

    records = [
        (
            chunk.id,
            chunk.repo_id,
            chunk.file_path,
            chunk.chunk_type.value,
            chunk.name,
            chunk.parent_name,
            chunk.content,
            chunk.start_line,
            chunk.end_line,
            chunk.embedding,  # None if not yet embedded
            chunk.content_hash,
            json.dumps(chunk.git_blame),
            json.dumps([c.model_dump() for c in chunk.commit_history]),
            chunk.imports,
            chunk.language.value,
            chunk.indexed_at,
        )
        for chunk in chunks
    ]

    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO code_chunks
                (id, repo_id, file_path, chunk_type, name, parent_name,
                 content, start_line, end_line, embedding, content_hash,
                 git_blame, commit_history, imports, language, indexed_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
            ON CONFLICT (id) DO NOTHING
            """,
            records,
        )

    logger.info("Inserted %d chunks", len(records))
    return len(records)


async def get_chunks_by_repo(repo_id: UUID) -> list[CodeChunk]:
    """Return all chunks belonging to a repository."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM code_chunks WHERE repo_id = $1 ORDER BY file_path, start_line",
        repo_id,
    )
    return [_row_to_chunk(r) for r in rows]


async def get_chunks_by_file(repo_id: UUID, file_path: str) -> list[CodeChunk]:
    """Return all chunks for a specific file within a repository."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM code_chunks WHERE repo_id = $1 AND file_path = $2 ORDER BY start_line",
        repo_id,
        file_path,
    )
    return [_row_to_chunk(r) for r in rows]


async def get_content_hashes(repo_id: UUID) -> dict[str, set[str]]:
    """Return a mapping of ``{file_path: {content_hash, …}}`` for all chunks
    in the repository.  Used to detect which files need re-indexing."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT file_path, content_hash FROM code_chunks WHERE repo_id = $1",
        repo_id,
    )
    result: dict[str, set[str]] = {}
    for row in rows:
        result.setdefault(row["file_path"], set()).add(row["content_hash"])
    return result


async def delete_chunks_by_file(repo_id: UUID, file_path: str) -> int:
    """Delete all chunks for a specific file.  Returns deleted count."""
    pool = await get_pool()
    result = await pool.execute(
        "DELETE FROM code_chunks WHERE repo_id = $1 AND file_path = $2",
        repo_id,
        file_path,
    )
    count = int(result.split()[-1])
    logger.debug("Deleted %d chunks for %s", count, file_path)
    return count


async def delete_chunks_by_repo(repo_id: UUID) -> int:
    """Delete all chunks for a repository.  Returns deleted count."""
    pool = await get_pool()
    result = await pool.execute(
        "DELETE FROM code_chunks WHERE repo_id = $1", repo_id
    )
    count = int(result.split()[-1])
    logger.info("Deleted %d chunks for repo %s", count, repo_id)
    return count


async def create_hnsw_index() -> None:
    """Create the HNSW index for vector search.

    Should be called AFTER bulk indexing for performance (Pitfall 3).
    Uses ``CONCURRENTLY`` to avoid table locks.
    """
    pool = await get_pool()
    logger.info("Creating HNSW index (this may take a moment)…")
    await pool.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunks_embedding
        ON code_chunks USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )
    logger.info("HNSW index created")


# ---------------------------------------------------------------------------
# Row ↔ Model helpers
# ---------------------------------------------------------------------------


def _row_to_repository(row: asyncpg.Record) -> Repository:
    return Repository(
        id=row["id"],
        name=row["name"],
        local_path=row["local_path"],
        languages=[Language(lang) for lang in (row["language"] or [])],
        last_indexed_at=row["last_indexed_at"],
        last_commit_hash=row["last_commit_hash"],
        chunk_count=row["chunk_count"],
        created_at=row["created_at"],
    )


def _row_to_chunk(row: asyncpg.Record) -> CodeChunk:
    commit_hist_raw = row["commit_history"]
    if isinstance(commit_hist_raw, str):
        commit_hist_raw = json.loads(commit_hist_raw)

    git_blame_raw = row["git_blame"]
    if isinstance(git_blame_raw, str):
        git_blame_raw = json.loads(git_blame_raw)

    return CodeChunk(
        id=row["id"],
        repo_id=row["repo_id"],
        file_path=row["file_path"],
        chunk_type=ChunkType(row["chunk_type"]),
        name=row["name"],
        parent_name=row["parent_name"],
        content=row["content"],
        start_line=row["start_line"],
        end_line=row["end_line"],
        embedding=list(row["embedding"]) if row["embedding"] else None,
        git_blame=git_blame_raw or {},
        commit_history=[CommitInfo(**c) for c in (commit_hist_raw or [])],
        imports=list(row["imports"] or []),
        language=Language(row["language"]),
        indexed_at=row["indexed_at"],
    )
