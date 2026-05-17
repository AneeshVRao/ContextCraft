# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-05-17

### Added
- **Dependency Graph** (`chunk_edges` table) — Static analyzer that resolves direct Python imports and class inheritance, mapping them to source and target chunk IDs with confidence scores.
- **Context Expansion** — Expands LLM context with 1-hop dependencies via recursive SQL query with cycle-guard. Adds `--with-deps` CLI flag and `expand_deps` API parameter.
- **Ollama LLM Provider** (`qwen2.5-coder:7b`) — Built-in `OllamaLLM` integration via `/api/chat` with `/api/tags` connection verification and streaming support.
- **Multi-Repo Search** — `hybrid_search` now performs Reciprocal Rank Fusion (RRF) normalization per-repo independently before merging, preventing large repos from drowning out small ones.
- **Multi-Repo Web UI** — `page.tsx` now uses a custom native HTML `<details>` dropdown for multi-selecting repos, plus a checkbox to toggle "Expand Graph Context".
- **Multi-Repo CLI/API** — Added `--repos` (comma-separated) and `--all-repos` CLI flags, and `repo_ids`/`all_repos` to the `/ask` endpoint schema.
- **Testing** — Added `tests/fixtures/import_ground_truth.txt` and `test_graph.py` to ensure high-fidelity edge generation. Integrated `@pytest.mark.unit` via ECC rules.

## [0.2.0] — 2026-05-17

### Added
- **Cohere Reranker** (`rerank-english-v3.0`) — cross-encoder reranking via `reranker/` module with abstract `BaseReranker` interface. Increases retrieval pool to 60 candidates, reranks down to requested `top_k`.
- **`--no-rerank` CLI flag** on `contextcraft ask` to bypass reranking when speed is preferred over precision.
- **Reranker in FastAPI** — `/ask` endpoint automatically reranks when `CONTEXTCRAFT_COHERE_API_KEY` is set.
- **RAG Evaluation Harness** (`eval/`) — `run_eval.py` measures source hit rate, LLM-as-a-judge faithfulness, and p50 latency across 10 benchmark queries. Includes `test_cases.json` and `README.md`.
- **Next.js 14 Web UI** (`web/`) — App Router, TypeScript, vanilla CSS dark-mode glassmorphism design:
  - Chat interface with SSE streaming (token-by-token rendering)
  - Repository selector dropdown
  - Source citations with Shiki syntax highlighting, line ranges, relevance scores, and git blame metadata
  - API proxy routes (`/api/ask`, `/api/repos`) to avoid CORS
  - Multi-stage Dockerfile for production builds
  - Added `web` service to `docker-compose.yml`
- **Background task tracking** in FastAPI — strong references to `asyncio.Task` objects prevent GC of indexing tasks.

### Changed
- Hybrid search now fetches 60 candidates (up from 20) when reranker is enabled.
- `pyproject.toml` — added `cohere>=5.0.0` dependency, `asyncpg` and `tree_sitter_languages` mypy overrides, ruff ignore rules for `E501`, `W293`, `UP042`, `B905`.

### Fixed
- All `ruff check` lint errors across 36 source files.
- All `ruff format` formatting inconsistencies across 15 files.
- All `mypy` type-check errors (21 → 0): added missing type annotations to `ast_parser.py`, fixed `AsyncIterator` return types in LLM base, handled `@computed_field` decorator stacking, cast untyped returns in `chunks_repo.py` and `ollama.py`.
- Fixed `test_imports_extracted` test — updated assertion after ruff removed unused `os` import from fixture.
- Replaced ambiguous EN DASH with hyphen in `context_builder.py`.

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
