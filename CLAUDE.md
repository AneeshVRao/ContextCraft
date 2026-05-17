# CLAUDE.md

This file provides guidance to AI coding agents when working with code in this repository.

## Project Overview

ContextCraft is a **semantic codebase indexer and Q&A engine**. It parses source code with tree-sitter, stores vector embeddings in PostgreSQL/pgvector, performs hybrid search (vector + BM25 via RRF), reranks with Cohere cross-encoder, and streams LLM-grounded answers via CLI, API, and Web UI.

## Architecture

- **Backend**: Python 3.11+, FastAPI, asyncpg, pgvector, Pydantic v2
- **Frontend**: Next.js 14 (App Router), TypeScript, vanilla CSS modules
- **Database**: PostgreSQL 16 + pgvector extension
- **Search**: Hybrid RRF (vector cosine + tsvector BM25), Cohere reranker
- **LLM**: OpenAI / Anthropic (swappable via `BaseLLM` ABC)
- **Embeddings**: OpenAI `text-embedding-3-small` / Ollama (swappable via `BaseEmbedder` ABC)

## Key Conventions

### Python Style
- **Formatter**: `ruff format` (not black)
- **Linter**: `ruff check` with rules: E, F, I, N, W, UP, B, SIM, RUF
- **Type checker**: `mypy --strict` (all functions must have type annotations)
- **Testing**: `pytest` with `asyncio_mode = "auto"`
- All imports sorted by `ruff` (isort-compatible)
- Use `from __future__ import annotations` in all modules

### Web (Next.js)
- App Router only (no Pages Router)
- Vanilla CSS modules — no Tailwind
- TypeScript strict mode

### Git Conventions
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `style:`, `refactor:`, `test:`, `docs:`, `chore:`
- Tag every release as `vX.Y.Z` (semver)
- Update `CHANGELOG.md` with every feature commit
- Update `README.md` when public API or architecture changes

## Running Tests

```bash
# Full CI suite (must all pass before push)
ruff format --check src/ tests/
ruff check src/ tests/
mypy src/contextcraft/
pytest tests/
```

## Project Structure

```
src/contextcraft/
├── api/main.py           # FastAPI server (SSE streaming)
├── cli/main.py           # Typer CLI (index, ask, status)
├── config.py             # Pydantic settings from env vars
├── models.py             # Core data models (CodeChunk, Repository, SearchResult)
├── parser/ast_parser.py  # tree-sitter AST → CodeChunk
├── embeddings/           # BaseEmbedder → OpenAI / Ollama
├── git/                  # blame + commit history extraction
├── db/                   # asyncpg connection pool + CRUD
├── search/               # vector, BM25, hybrid RRF, context builder
├── reranker/             # BaseReranker → Cohere cross-encoder
└── llm/                  # BaseLLM → OpenAI / Anthropic

web/                      # Next.js 14 frontend
eval/                     # RAG evaluation harness
docker/                   # Dockerfile + docker-compose.yml
tests/                    # pytest suite
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CONTEXTCRAFT_OPENAI_API_KEY` | Yes | — | OpenAI API key for embeddings + LLM |
| `CONTEXTCRAFT_DB_URL` | Yes | `postgresql://...` | PostgreSQL connection string |
| `CONTEXTCRAFT_COHERE_API_KEY` | No | — | Enables Cohere reranking |
| `CONTEXTCRAFT_RERANK_ENABLED` | No | `true` | Toggle reranker |
| `CONTEXTCRAFT_RERANK_MODEL` | No | `rerank-english-v3.0` | Cohere model |
| `CONTEXTCRAFT_LLM_PROVIDER` | No | `openai` | `openai` or `anthropic` |

## Common Patterns

- **Abstract bases**: All swappable components use ABCs (`BaseLLM`, `BaseEmbedder`, `BaseReranker`)
- **Async everything**: Database, embeddings, LLM calls, and search are all async
- **SSE streaming**: Both CLI and API stream LLM responses token-by-token
- **Pydantic v2**: Models use `BaseModel` with `computed_field` for derived properties
