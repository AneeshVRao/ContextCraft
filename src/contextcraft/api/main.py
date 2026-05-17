"""FastAPI application for ContextCraft.

Provides REST endpoints:
    GET  /health    — Health check
    GET  /repos     — List indexed repositories
    POST /index     — Trigger indexing of a repository
    POST /ask       — Ask a question (SSE streaming)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from contextcraft.config import settings
from contextcraft.db import chunks_repo
from contextcraft.db.connection import close_pool, run_migrations
from contextcraft.embeddings.base import BaseEmbedder
from contextcraft.embeddings.gemini import GeminiEmbedder
from contextcraft.embeddings.openai import OpenAIEmbedder
from contextcraft.models import SearchResult
from contextcraft.search.context_builder import build_context, format_sources
from contextcraft.search.hybrid import hybrid_search

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task[Any]] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore
    """Startup: connect to DB and run migrations.  Shutdown: close pool."""
    await run_migrations()
    yield
    await close_pool()


app = FastAPI(
    title="ContextCraft API",
    description="Index codebases and ask questions with full context.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class IndexRequest(BaseModel):
    repo_path: str
    incremental: bool = False
    skip_embeddings: bool = False
    skip_git: bool = False


class AskRequest(BaseModel):
    question: str
    repo_ids: list[str] | None = None
    all_repos: bool = False
    top_k: int = 10
    expand_deps: bool = False


class RepoResponse(BaseModel):
    id: str
    name: str
    local_path: str
    languages: list[str]
    chunk_count: int
    last_indexed_at: str | None


class HealthResponse(BaseModel):
    status: str
    version: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok", version="0.1.0")


@app.get("/repos", response_model=list[RepoResponse])
async def list_repos() -> list[RepoResponse]:
    """List all indexed repositories."""
    repos = await chunks_repo.list_repositories()
    return [
        RepoResponse(
            id=str(r.id),
            name=r.name,
            local_path=r.local_path,
            languages=[lang.value for lang in r.languages],
            chunk_count=r.chunk_count,
            last_indexed_at=(r.last_indexed_at.isoformat() if r.last_indexed_at else None),
        )
        for r in repos
    ]


@app.post("/index")
async def index_repo(request: IndexRequest) -> dict[str, str]:
    """Trigger indexing of a repository (runs in background)."""
    repo_path = Path(request.repo_path).resolve()
    if not repo_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {repo_path}")

    # Import the CLI's internal indexing function
    from contextcraft.cli.main import _index_async

    # Run indexing in background
    # Store reference to task to avoid it being garbage collected
    task = asyncio.create_task(
        _index_async(
            repo_path,
            incremental=request.incremental,
            skip_embeddings=request.skip_embeddings,
            skip_git=request.skip_git,
        )
    )
    # Fire and forget pattern that keeps a strong reference
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {"status": "indexing_started", "repo_path": str(repo_path)}


@app.post("/ask")
async def ask_question(request: AskRequest) -> EventSourceResponse:
    """Ask a question about an indexed codebase (SSE streaming)."""
    if settings.embedding_provider == "openai" and not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
    elif settings.embedding_provider == "gemini" and not settings.gemini_api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")
    # Find repository
    repos = await chunks_repo.list_repositories()
    if not repos:
        raise HTTPException(status_code=404, detail="No repositories indexed")

    target_repos = []
    if request.all_repos:
        target_repos = repos
    elif request.repo_ids:
        # Resolve requested IDs/names
        for rid in request.repo_ids:
            found = next((r for r in repos if str(r.id) == rid or r.name == rid), None)
            if found:
                target_repos.append(found)
        if not target_repos:
            raise HTTPException(
                status_code=404, detail="None of the requested repositories were found"
            )
    else:
        # Default: most recently indexed repo
        target_repos = [repos[0]]

    target_repo_ids = [r.id for r in target_repos]
    # We use the first repo's path for disk context, as cross-repo disk context
    # gets complicated (would need to track which repo each chunk came from).
    # In a full cross-repo implementation, we'd add repo_path to CodeChunk.
    primary_repo_path = target_repos[0].local_path

    embedder: BaseEmbedder = (
        GeminiEmbedder() if settings.embedding_provider == "gemini" else OpenAIEmbedder()
    )

    query_embedding = await embedder.embed_single(request.question)

    # Search
    use_reranker = settings.rerank_enabled and bool(settings.cohere_api_key)
    fetch_k = 20 if use_reranker else request.top_k

    results = await hybrid_search(
        query_embedding=query_embedding,
        query_text=request.question,
        repo_ids=target_repo_ids,
        top_k=fetch_k,
    )

    if not results:
        raise HTTPException(status_code=404, detail="No relevant code found")

    # Rerank
    if use_reranker:
        from contextcraft.reranker.cohere import CohereReranker

        reranker = CohereReranker()
        results = await reranker.rerank(request.question, results, request.top_k)

    # Expand with dependency chunks if requested
    dep_results: list[SearchResult] | None = None
    if request.expand_deps:
        try:
            from contextcraft.graph.expander import expand_with_deps

            chunk_ids = [sr.chunk.id for sr in results]
            dep_chunks = await expand_with_deps(chunk_ids)
            if dep_chunks:
                dep_results = [
                    SearchResult(chunk=dc, score=0.0, rank=len(results) + i)
                    for i, dc in enumerate(dep_chunks)
                ]
        except Exception:
            pass  # gracefully skip if graph not available

    # Build context
    context = build_context(
        results,
        repo_path=primary_repo_path,
        expand_deps=request.expand_deps,
        dep_chunks=dep_results,
    )
    sources = format_sources(results)

    # LLM system prompt
    system_prompt = """You are ContextCraft, an expert code analysis assistant.
You answer questions about codebases using the provided code context.
Base your answers ONLY on the provided code context.
Reference specific file paths and line numbers when explaining code.
Be concise but thorough. Use markdown formatting."""

    user_message = f"## Code Context\n\n{context}\n\n## Question\n\n{request.question}"

    # Stream response via SSE
    async def event_generator() -> AsyncIterator[dict[str, Any]]:
        from contextcraft.llm.base import BaseLLM
        from contextcraft.llm.openai import OpenAILLM

        llm: BaseLLM
        if settings.llm_provider == "anthropic":
            from contextcraft.llm.anthropic import AnthropicLLM

            llm = AnthropicLLM()
        elif settings.llm_provider == "ollama":
            from contextcraft.llm.ollama import OllamaLLM

            llm = OllamaLLM()
        elif settings.llm_provider == "gemini":
            from contextcraft.llm.gemini import GeminiLLM

            llm = GeminiLLM()
        else:
            llm = OpenAILLM()

        try:
            async for token in llm.stream(system_prompt, user_message):
                yield {"event": "token", "data": token}
        except asyncio.CancelledError:
            # Client disconnected mid-stream — stop consuming LLM tokens
            # to avoid burning API credits silently.
            logger.info("SSE client disconnected — stopping LLM stream")
            raise

        # Send sources as final event
        yield {"event": "sources", "data": sources}
        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Run with uvicorn
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "contextcraft.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
