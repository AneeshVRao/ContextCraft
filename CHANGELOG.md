# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Gemini provider** — Default embeddings (`text-embedding-004`) and chat (`gemini-1.5-flash`) via `google-genai`; zero-cost local dev with a free AI Studio key.
- **Production startup checks** (`startup.py`) — API lifespan verifies PostgreSQL, pgvector extension, provider API keys, and Ollama reachability when configured.
- **Security module** (`security.py`) — Repo path validation (blocks sensitive dirs and symlink escape), query sanitization (500-char cap, control-char strip), Ollama URL SSRF guard (localhost-only unless `CONTEXTCRAFT_OLLAMA_ALLOW_REMOTE=true`).
- **API rate limiting** — `slowapi` on `POST /ask` (10 requests/minute per IP).
- **Configurable CORS** — `CONTEXTCRAFT_ALLOWED_ORIGINS` (comma-separated); defaults to local Next.js dev origins (not `*`).
- **Async git subprocesses** — `git/async_git.py`; blame and log no longer block the event loop during indexing.
- **HTTP timeouts** — Shared `http_timeouts.py` for Ollama and outbound clients (connect/read caps).
- **PyPI packaging** — `py.typed` marker, `slowapi` runtime dependency, hatchling wheel build.
- **Railway deploy config** — `railway.toml` with `/health` check, `restartPolicyType = on_failure`, `$PORT` binding.
- **Docker hardening** — Multi-stage image runs as non-root `appuser`; `PORT` env respected in CMD.

### Changed
- **Default providers** — `embedding_provider` and `llm_provider` default to `gemini` (OpenAI and Anthropic remain swappable).
- **`DATABASE_URL` alias** — Railway/Heroku-style `DATABASE_URL` accepted alongside `CONTEXTCRAFT_DATABASE_URL`.
- **Cohere reranker errors** — Raises `RerankerUnavailableError` with RRF fallback instead of opaque failures; API emits a warning SSE event when reranking is skipped.
- **Tree-sitter parsing** — CPU-bound `parse_file` runs in a thread pool via `parse_file_async` during async indexing.
- **`.gitignore`** — Comprehensive stack coverage (Python, Next.js, Docker, eval outputs, IDE, Railway); `CLAUDE.md` kept local-only (not in public repo).

### Fixed
- Datetime defaults use timezone-aware `datetime.now(UTC)` (no deprecated `utcnow()`).
- OpenAI SSE streams close cleanly on client disconnect (`CancelledError`).
- Ollama embedder/LLM use validated base URLs and explicit timeouts.

## [0.3.0] — 2026-05-17

### Added
- **Dependency graph** (`chunk_edges` table) — Static analyzer that resolves direct Python imports and class inheritance, mapping them to source and target chunk IDs with confidence scores.
- **Context expansion** — Expands LLM context with 1-hop dependencies; cycle guard via `visited` set in `graph.expander`. Adds `--with-deps` CLI flag and `expand_deps` API parameter.
- **Ollama LLM provider** (`qwen2.5-coder:7b`) — `OllamaLLM` via `/api/chat` with `/api/tags` connection verification and streaming support.
- **Multi-repo search** — `hybrid_search` performs RRF normalization per repo before merging, so large repos do not drown out small ones.
- **Multi-repo Web UI** — Repo multi-select and “Expand Graph Context” toggle in `web/src/app/page.tsx`.
- **Multi-repo CLI/API** — `--repos` / `--all-repos` CLI flags; `repo_ids` / `all_repos` on `/ask`.
- **Benchmark harness** — `BENCHMARK.md` and eval tooling for source hit rate and latency.
- **Testing** — `tests/fixtures/import_ground_truth.txt` and `test_graph.py` for dependency edge generation.

## [0.2.0] — 2026-05-17

### Added
- **Cohere reranker** (`rerank-english-v3.0`) — cross-encoder reranking via `reranker/` module with abstract `BaseReranker` interface. Increases retrieval pool to 60 candidates, reranks down to requested `top_k`.
- **`--no-rerank` CLI flag** on `contextcraft ask` to bypass reranking when speed is preferred over precision.
- **Reranker in FastAPI** — `/ask` endpoint automatically reranks when `CONTEXTCRAFT_COHERE_API_KEY` is set.
- **RAG evaluation harness** (`eval/`) — `run_eval.py` measures source hit rate, LLM-as-a-judge faithfulness, and p50 latency across 10 benchmark queries. Includes `test_cases.json` and `README.md`.
- **Next.js Web UI** (`web/`) — App Router, TypeScript, vanilla CSS dark-mode design:
  - Chat interface with SSE streaming (token-by-token rendering)
  - Repository selector dropdown
  - Source citations with Shiki syntax highlighting, line ranges, relevance scores, and git blame metadata
  - API proxy routes (`/api/ask`, `/api/repos`) to avoid CORS
  - Multi-stage Dockerfile for production builds
  - `web` service in `docker-compose.yml`
- **Background task tracking** in FastAPI — strong references to `asyncio.Task` objects prevent GC of indexing tasks.

### Changed
- Hybrid search now fetches 60 candidates (up from 20) when reranker is enabled.
- `pyproject.toml` — added `cohere>=5.0.0` dependency, mypy overrides, ruff ignore rules for `E501`, `W293`, `UP042`, `B905`.

### Fixed
- All `ruff check` lint errors across 36 source files.
- All `ruff format` formatting inconsistencies across 15 files.
- All `mypy --strict` type-check errors (21 → 0).
- Fixed `test_imports_extracted` test after ruff removed unused import from fixture.
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
- **GitHub Actions CI**: ruff format → ruff check → mypy `--strict` → pytest.
- **Incremental indexing**: `--incremental` flag re-indexes only files changed since last commit.
- **`.gitignore` / `.contextignore` support**: skips binary files, `node_modules`, etc.
