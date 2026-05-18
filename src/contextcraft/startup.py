"""FastAPI startup health checks."""

from __future__ import annotations

import logging

import httpx

from contextcraft.config import settings
from contextcraft.db.connection import get_pool
from contextcraft.http_timeouts import OLLAMA_TIMEOUT
from contextcraft.security import validate_ollama_base_url

logger = logging.getLogger(__name__)


async def verify_startup() -> None:
    """Verify external dependencies before serving traffic."""
    await _check_postgres()
    _check_embedding_provider()
    await _check_llm_provider()
    _check_reranker()


async def _check_postgres() -> None:
    try:
        pool = await get_pool()
    except RuntimeError as exc:
        msg = (
            f"PostgreSQL unreachable at {settings.database_url!r}. "
            "Is docker compose up? Original error: "
            f"{exc}"
        )
        raise RuntimeError(msg) from exc

    async with pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
        has_vector = await conn.fetchval(
            "SELECT 1 FROM pg_extension WHERE extname = 'vector' LIMIT 1"
        )
    if not has_vector:
        msg = "pgvector extension is not installed. Run: CREATE EXTENSION IF NOT EXISTS vector;"
        raise RuntimeError(msg)


def _check_embedding_provider() -> None:
    if settings.embedding_provider == "openai" and not settings.openai_api_key:
        msg = "CONTEXTCRAFT_OPENAI_API_KEY is required when embedding_provider=openai"
        raise RuntimeError(msg)
    if settings.embedding_provider == "gemini" and not settings.gemini_api_key:
        msg = "CONTEXTCRAFT_GEMINI_API_KEY is required when embedding_provider=gemini"
        raise RuntimeError(msg)


async def _check_llm_provider() -> None:
    provider = settings.llm_provider
    if provider == "openai" and not settings.openai_api_key:
        msg = "CONTEXTCRAFT_OPENAI_API_KEY is required when llm_provider=openai"
        raise RuntimeError(msg)
    if provider == "anthropic" and not settings.anthropic_api_key:
        msg = "CONTEXTCRAFT_ANTHROPIC_API_KEY is required when llm_provider=anthropic"
        raise RuntimeError(msg)
    if provider == "gemini" and not settings.gemini_api_key:
        msg = "CONTEXTCRAFT_GEMINI_API_KEY is required when llm_provider=gemini"
        raise RuntimeError(msg)
    if provider == "ollama":
        base_url = validate_ollama_base_url(
            settings.ollama_base_url,
            allow_remote=settings.ollama_allow_remote,
        )
        try:
            async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
                resp = await client.get(f"{base_url}/api/tags")
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            msg = (
                f"Ollama unreachable at {base_url}. "
                "Start it with: ollama serve. "
                f"Original error: {exc}"
            )
            raise RuntimeError(msg) from exc


def _check_reranker() -> None:
    if settings.rerank_enabled and not settings.cohere_api_key:
        logger.warning(
            "Reranking enabled but CONTEXTCRAFT_COHERE_API_KEY is unset; reranking will be skipped"
        )
