"""Async PostgreSQL connection pool with retry logic.

Provides ``get_pool()`` to obtain a shared ``asyncpg.Pool`` and
``run_migrations()`` to apply SQL migration files on startup.

Pool sizing rationale
---------------------
The CLI indexer and the FastAPI server can run concurrently.  Indexing
uses up to ~3 connections (bulk insert, delete, metadata update) while
the API server needs connections for search queries.  We size the pool
to handle both workloads simultaneously:
  - min_size = 2  (always ready for quick queries)
  - max_size = 20 (room for indexing + concurrent API requests)

If the pool is exhausted, ``asyncpg`` raises
``asyncpg.InterfaceError`` (not a Postgres-level error) and we handle
it with a clear message rather than a silent hang.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import asyncpg

from contextcraft.config import settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def get_pool() -> asyncpg.Pool:
    """Return the global connection pool, creating it on first call.

    Retries up to 5 times with exponential back-off if the database is
    not yet available (common when waiting for Docker containers).
    Handles ``TooManyConnectionsError`` specifically with a clear
    diagnostic message.
    """
    global _pool
    if _pool is not None:
        return _pool

    last_exc: Exception | None = None
    for attempt in range(1, 6):
        try:
            _pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=settings.db_min_connections,
                max_size=settings.db_max_connections,
                # Prevent silent hangs: fail fast if no connection is
                # available within 30s rather than blocking forever.
                command_timeout=60,
            )
            logger.info("Database pool created (attempt %d)", attempt)
            return _pool

        except asyncpg.TooManyConnectionsError as exc:
            # This is a server-level "too many clients" error — retrying
            # won't help unless other clients disconnect.  Surface it
            # immediately so the operator can fix pool sizing or close
            # stale connections.
            raise RuntimeError(
                f"PostgreSQL server refused connection (too many clients). "
                f"Current pool max_size={settings.db_max_connections}. "
                f"Increase max_connections in postgresql.conf or reduce "
                f"pool size.  Original error: {exc}"
            ) from exc

        except (asyncpg.PostgresError, OSError) as exc:
            last_exc = exc
            wait = min(2**attempt, 16)
            logger.warning(
                "DB connection failed (attempt %d/%d): %s — retrying in %ds",
                attempt,
                5,
                exc,
                wait,
            )
            await asyncio.sleep(wait)

    raise RuntimeError(f"Could not connect to database after 5 attempts: {last_exc}")


async def close_pool() -> None:
    """Gracefully close the connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


async def run_migrations() -> None:
    """Apply all SQL migration files in order.

    Migrations are idempotent (``CREATE … IF NOT EXISTS``), so running
    them multiple times is safe.
    """
    pool = await get_pool()
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    async with pool.acquire() as conn:
        for mig in migration_files:
            sql = mig.read_text(encoding="utf-8")
            logger.info("Applying migration: %s", mig.name)
            await conn.execute(sql)

    logger.info("All migrations applied (%d files)", len(migration_files))
