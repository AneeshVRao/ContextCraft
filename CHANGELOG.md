# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-05-17

### Added
- **Tree-sitter AST parser** for Python, JavaScript/TypeScript, and Go — extracts functions, classes, and modules as semantic chunks (not fixed-size splits).
- **PostgreSQL + pgvector** storage with async connection pool (asyncpg), retry logic, and full CRUD for repositories and code chunks.
- **Hybrid search** via Reciprocal Rank Fusion (RRF) combining pgvector cosine similarity and PostgreSQL tsvector full-text search in a single SQL query.
- **Git blame + commit history** per chunk — runs `git blame --porcelain` once per file (not per chunk) for 50x speedup.
- **CLI** (`contextcraft index`, `contextcraft ask`, `contextcraft status`) built with Typer and Rich progress bars.
- **FastAPI API server** with `/health`, `/repos`, `/index`, and `/ask` (SSE streaming) endpoints.
- **Embeddings pipeline** with OpenAI `text-embedding-3-small` and Ollama support via abstract `BaseEmbedder` interface.
- **LLM providers**: OpenAI and Anthropic Claude, swappable via config, with streaming support.
- **Docker Compose** for local pgvector, multi-stage Dockerfile for production.
- **GitHub Actions CI**: ruff lint → mypy type-check → pytest.
- **Incremental indexing**: `--incremental` flag re-indexes only files changed since last commit.
- **`.gitignore` / `.contextignore` support**: skips binary files, node_modules, etc.
