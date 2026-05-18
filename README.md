# ContextCraft

**CLI + API + Web UI that indexes any codebase with tree-sitter, stores semantic chunks in pgvector, reranks with Cohere, and answers engineering questions with full file and git-history context.**

[![CI](https://github.com/AneeshVRao/ContextCraft/actions/workflows/ci.yml/badge.svg)](https://github.com/AneeshVRao/ContextCraft/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## What it does

ContextCraft turns a codebase into a searchable knowledge base:

1. **Parses** source with [tree-sitter](https://tree-sitter.github.io/) — functions, classes, and modules as semantic chunks (not fixed-size splits).
2. **Builds a graph** — resolves Python imports and inheritance into `chunk_edges` for dependency-aware context.
3. **Enriches** chunks with git blame and per-file commit history.
4. **Embeds** chunks (default: Google Gemini `text-embedding-004`) and stores vectors in PostgreSQL + [pgvector](https://github.com/pgvector/pgvector).
5. **Searches** with hybrid Reciprocal Rank Fusion (RRF): vector cosine + PostgreSQL full-text, including **multi-repo** queries.
6. **Reranks** with [Cohere](https://cohere.com/) cross-encoder (`rerank-english-v3.0`) when an API key is set.
7. **Answers** via Gemini, OpenAI, Anthropic, or local **Ollama**, grounded in retrieved code with paths and line numbers.
8. **Streams** responses over SSE to the CLI and the Next.js web UI.

See [BENCHMARK.md](BENCHMARK.md) for measured source hit rate and latency. See [CHANGELOG.md](CHANGELOG.md) for release history.

---

## Quick start

### Prerequisites

| Requirement | Purpose |
|-------------|---------|
| Python 3.11+ | CLI, API, indexing |
| Docker | PostgreSQL 16 + pgvector |
| Git | Blame and history during index |
| [Gemini API key](https://aistudio.google.com/app/apikey) | Default embeddings + chat (free tier) |
| [Cohere API key](https://dashboard.cohere.com/api-keys) | Optional reranking |
| Node.js 18+ | Web UI only |

### 1. Install

```bash
git clone https://github.com/AneeshVRao/ContextCraft.git
cd ContextCraft
python -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### 2. Database

```bash
docker compose -f docker/docker-compose.yml up -d postgres
```

### 3. Environment

```bash
cp .env.example .env
```

Set at minimum:

```env
CONTEXTCRAFT_GEMINI_API_KEY=your_key_here
# Optional:
# CONTEXTCRAFT_COHERE_API_KEY=...
```

Railway and similar hosts can set `DATABASE_URL` instead of `CONTEXTCRAFT_DATABASE_URL`.

### 4. Index and ask (CLI)

```bash
contextcraft index ./path/to/your/project
contextcraft status
contextcraft ask "How does hybrid search work?"
```

### 5. Full stack (API + Web UI)

**Terminal 1 — API**

```bash
uvicorn contextcraft.api.main:app --reload --host 0.0.0.0 --port 8000
```

Startup verifies Postgres, pgvector, and configured provider keys. Health check: `GET http://localhost:8000/health`.

**Terminal 2 — Web UI**

```bash
cd web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The UI proxies to the API via `API_URL` (default `http://127.0.0.1:8000`).

---

## CLI reference

### `contextcraft index <repo_path>`

Parse → git metadata → embed → store. Rejects sensitive paths (e.g. `~/.ssh`, `/etc`) and symlink escapes outside the repo root.

```bash
contextcraft index ./my-project
contextcraft index ./my-project --incremental
contextcraft index ./my-project --skip-embeddings   # parse only
contextcraft index ./my-project --skip-git
```

### `contextcraft ask "question"`

Streams an answer to the terminal. Questions are sanitized (max 500 characters, control characters stripped).

```bash
contextcraft ask "Where is authentication handled?"
contextcraft ask "Explain the DB pool" --all-repos
contextcraft ask "Caching layer" --repos repo-a,repo-b
contextcraft ask "Database client setup" --with-deps
contextcraft ask "Quick lookup" --no-rerank
```

### `contextcraft status`

Lists indexed repositories, languages, chunk counts, and last index time.

---

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | `{"status":"ok","version":"…"}` |
| `GET` | `/repos` | Indexed repositories |
| `POST` | `/index` | Start background indexing (`repo_path`, optional flags) |
| `POST` | `/ask` | SSE stream: `token`, `sources`, `done` (and `warning` if rerank skipped) |

`POST /ask` is rate-limited to **10 requests/minute per IP**.

```bash
curl http://localhost:8000/health
```

---

## Configuration

All settings use the `CONTEXTCRAFT_` prefix (see `.env.example`). Common variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` / `CONTEXTCRAFT_DATABASE_URL` | `postgresql://contextcraft:…@localhost:5432/contextcraft` | Postgres connection |
| `CONTEXTCRAFT_GEMINI_API_KEY` | — | Gemini embeddings + chat (default providers) |
| `CONTEXTCRAFT_EMBEDDING_PROVIDER` | `gemini` | `gemini` or `openai` |
| `CONTEXTCRAFT_LLM_PROVIDER` | `gemini` | `gemini`, `openai`, `anthropic`, `ollama` |
| `CONTEXTCRAFT_OPENAI_API_KEY` | — | Required when using OpenAI provider |
| `CONTEXTCRAFT_COHERE_API_KEY` | — | Enables Cohere reranking |
| `CONTEXTCRAFT_RERANK_ENABLED` | `true` | Toggle reranker |
| `CONTEXTCRAFT_ALLOWED_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | CORS origins (comma-separated) |
| `CONTEXTCRAFT_OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama (localhost only by default) |
| `CONTEXTCRAFT_OLLAMA_ALLOW_REMOTE` | `false` | Allow non-localhost Ollama URLs (SSRF risk) |
| `CONTEXTCRAFT_SEARCH_TOP_K` | `10` | Chunks returned after search/rerank |
| `CONTEXTCRAFT_API_PORT` | `8000` | API listen port |

### Alternative providers

**OpenAI** (embeddings + chat):

```env
CONTEXTCRAFT_EMBEDDING_PROVIDER=openai
CONTEXTCRAFT_LLM_PROVIDER=openai
CONTEXTCRAFT_OPENAI_API_KEY=sk-...
```

**Ollama** (local chat only; embeddings still need Gemini or OpenAI unless you customize):

```env
CONTEXTCRAFT_LLM_PROVIDER=ollama
CONTEXTCRAFT_OLLAMA_MODEL=qwen2.5-coder:7b
```

Run `ollama serve` and pull the model first.

---

## Deployment

### Railway

`railway.toml` is included. Set `DATABASE_URL`, provider API keys, and `CONTEXTCRAFT_ALLOWED_ORIGINS` to your frontend URL. Deploy uses `docker/Dockerfile` or the configured start command with `$PORT`.

### Docker (API image)

```bash
docker build -f docker/Dockerfile -t contextcraft .
docker run -p 8000:8000 --env-file .env contextcraft
```

The runtime image runs as a non-root user and honors `PORT`.

### PyPI (local build)

```bash
pip install build
python -m build --wheel
pip install dist/contextcraft-*.whl
contextcraft --help
```

---

## Architecture

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────────┐
│ tree-sitter  │────▶│ CodeChunks      │────▶│ pgvector         │
│ AST parse    │     │ + git blame     │     │ PostgreSQL       │
└──────────────┘     └────────┬────────┘     └────────┬─────────┘
                              │                       │
                     ┌────────▼────────┐              │
                     │ chunk_edges     │              │
                     │ (imports/       │              │
                     │  inherits)      │              │
                     └────────┬────────┘              │
                              │                       │
                     ┌────────▼────────┐     ┌───────▼─────────┐
                     │ Hybrid RRF      │◀────│ Vector + BM25   │
                     └────────┬────────┘     └─────────────────┘
                              │
                     ┌────────▼────────┐
                     │ Cohere rerank   │ (optional)
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐     ┌─────────────────┐
                     │ Context + LLM   │────▶│ Next.js UI      │
                     │ (SSE)           │     │ CLI             │
                     └─────────────────┘     └─────────────────┘
```

**Design notes**

- AST chunking beats fixed token windows for code Q&A.
- Single Postgres instance holds metadata, vectors, and FTS — no separate vector DB.
- Per-file `git blame` (one subprocess per file, async during index).
- RRF merges rankings without score normalization headaches.
- Dependency expansion uses a 1-hop query plus a `visited` set for cycle safety.

---

## Supported languages

| Language | Extensions |
|----------|------------|
| Python | `.py` |
| JavaScript | `.js`, `.jsx` |
| TypeScript | `.ts`, `.tsx` |
| Go | `.go` |

ContextCraft pins `tree-sitter<0.22.0` for compatibility with `tree-sitter-languages`. Some newer grammar features may be unsupported; see tests under `tests/test_parser.py`.

---

## Evaluation

```bash
python eval/run_eval.py
python eval/run_eval.py --rerank
```

Measures source hit rate, faithfulness, and latency. Details: [`eval/README.md`](eval/README.md).

---

## Development

CI must pass before merge:

```bash
ruff format --check src/ tests/
ruff check src/ tests/
mypy src/contextcraft/ --strict
pytest tests/ -v --tb=short
```

```bash
pip install -e ".[dev]"
pytest
ruff format src/ tests/
```

---

## Project structure

```
contextcraft/
├── src/contextcraft/
│   ├── cli/main.py           # Typer CLI
│   ├── api/main.py           # FastAPI + SSE + rate limits
│   ├── parser/ast_parser.py  # tree-sitter → CodeChunk
│   ├── graph/                # Dependency resolver + expander
│   ├── embeddings/           # Gemini, OpenAI, Ollama
│   ├── git/                  # Async blame + history
│   ├── db/                   # asyncpg pool + migrations
│   ├── search/               # Vector, BM25, hybrid RRF
│   ├── reranker/             # Cohere cross-encoder
│   ├── llm/                  # Gemini, OpenAI, Anthropic, Ollama
│   ├── security.py           # Path + query + Ollama URL policy
│   └── startup.py            # API startup health checks
├── web/                      # Next.js UI (App Router)
├── eval/                     # RAG evaluation harness
├── tests/
├── docker/
│   ├── Dockerfile            # Production API image (non-root)
│   └── docker-compose.yml    # Postgres (+ optional web)
├── railway.toml
├── pyproject.toml
├── CHANGELOG.md
└── .env.example
```

---

## Roadmap

- [x] Phase 1: Core CLI — parser, pgvector, hybrid search
- [x] Phase 2: Cohere reranker, eval harness, Next.js UI
- [x] Phase 3: Dependency graph, multi-repo search, Ollama LLM
- [x] Phase 3b: Gemini defaults, production hardening, Railway/Docker
- [ ] Phase 4: File watcher (live re-index), temporal queries, VS Code extension
- [ ] Phase 5: PyPI publish, marketing site

---

## License

MIT
