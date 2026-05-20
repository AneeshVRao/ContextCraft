# ContextCraft

**CLI + API + Web UI that indexes any codebase with tree-sitter, stores semantic chunks in pgvector, reranks with Cohere, and answers engineering questions with full file and git-history context.**

[![CI](https://github.com/AneeshVRao/ContextCraft/actions/workflows/ci.yml/badge.svg)](https://github.com/AneeshVRao/ContextCraft/actions)
[![PyPI](https://img.shields.io/pypi/v/contextcraft-py.svg)](https://pypi.org/project/contextcraft-py/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## What it does

ContextCraft turns any codebase into a searchable knowledge base that understands
code structure — not just text.

1. **Parses** source with [tree-sitter](https://tree-sitter.github.io/) — functions,
   classes, and modules as semantic chunks, never mid-function splits.
2. **Builds a dependency graph** — resolves Python imports and class inheritance into
   `chunk_edges` for context expansion across file boundaries.
3. **Enriches** every chunk with `git blame` author metadata and per-file commit history.
4. **Embeds** chunks (default: Gemini `gemini-embedding-2`) and stores vectors in
   PostgreSQL + [pgvector](https://github.com/pgvector/pgvector) with an HNSW index.
5. **Searches** with hybrid Reciprocal Rank Fusion — vector cosine similarity and
   PostgreSQL full-text search merged without raw score normalization.
   Supports simultaneous **multi-repo** queries with per-repo RRF normalization
   to prevent large codebases from drowning out smaller ones.
6. **Reranks** with [Cohere](https://cohere.com/) `rerank-english-v3.0` when an
   API key is configured — fetches 20 candidates, reranks to top 10.
7. **Answers** via Gemini, OpenAI, Anthropic, or local **Ollama**, grounded in
   retrieved code with file paths, line numbers, and git author context.
8. **Streams** responses over SSE to both the CLI and the Next.js web UI.

---

## Performance

Evaluated against ContextCraft's own codebase (v0.3.0), 10 hand-curated questions,
3 iterations each. Full methodology and per-question breakdown: [BENCHMARK.md](BENCHMARK.md).

| Configuration | Source Hit Rate | Faithful Answers | P50 Latency |
|---|---|---|---|
| RRF only | **80.0%** | 73.3% | 3,876ms |
| RRF + Reranker | 75.0% | 60.0% | 5,121ms |
| RRF + Reranker + Deps | 75.0% | 53.3% | 4,993ms |

*Source Hit Rate: target file appeared in retrieved context (position-agnostic).
Latency is retrieval only; LLM generation adds 2–15s depending on model.*

---

## Install

### From PyPI (recommended)

```bash
pip install contextcraft-py
```

### From source (development)

```bash
git clone https://github.com/AneeshVRao/ContextCraft.git
cd ContextCraft
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

---

## Quick start

### Prerequisites

| Requirement | Purpose |
|---|---|
| Python 3.11+ | CLI, API, indexing |
| Docker | PostgreSQL 16 + pgvector |
| Git | Blame and history during index |
| [Gemini API key](https://aistudio.google.com/app/apikey) | Default embeddings + LLM (free tier) |
| [Cohere API key](https://dashboard.cohere.com/api-keys) | Optional — enables reranking |
| Node.js 18+ | Web UI only |

### 1. Start the database

```bash
docker compose -f docker/docker-compose.yml up -d postgres
```

### 2. Configure environment

```bash
cp .env.example .env
```

Set at minimum:

```env
CONTEXTCRAFT_GEMINI_API_KEY=your_key_here

# Optional — enables Cohere reranking
# CONTEXTCRAFT_COHERE_API_KEY=your_key_here
```

### 3. Index and ask

```bash
contextcraft index ./path/to/your/project
contextcraft status
contextcraft ask "How does authentication work?"
```

### 4. Full stack (API + Web UI)

**Terminal 1 — API server**

```bash
uvicorn contextcraft.api.main:app --reload --host 0.0.0.0 --port 8000
```

Startup verifies Postgres, pgvector, and configured provider keys.
Health check: `GET http://localhost:8000/health`

**Terminal 2 — Web UI**

```bash
cd web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## CLI reference

### `contextcraft index <repo_path>`

Parse → git metadata → embed → store. Rejects sensitive paths (`~/.ssh`, `/etc`)
and symlink escapes outside the repo root.

```bash
contextcraft index ./my-project
contextcraft index ./my-project --incremental     # only changed files
contextcraft index ./my-project --skip-git        # skip blame/history
contextcraft index ./my-project --skip-embeddings # parse and store only
```

### `contextcraft ask "question"`

Streams an answer to the terminal. Queries are sanitized (max 500 characters,
control characters stripped).

```bash
contextcraft ask "Where is authentication handled?"
contextcraft ask "Explain the DB pool" --all-repos
contextcraft ask "Caching layer" --repos repo-a,repo-b
contextcraft ask "Database client setup" --with-deps   # expand 1-hop imports
contextcraft ask "Quick lookup" --no-rerank            # skip Cohere, lower latency
```

### `contextcraft status`

Lists indexed repositories, languages, chunk counts, and last index time.

---

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | `{"status":"ok","version":"…"}` |
| `GET` | `/repos` | List indexed repositories |
| `POST` | `/index` | Start background indexing |
| `POST` | `/ask` | SSE stream: `token`, `sources`, `done` events |

`POST /ask` is rate-limited to **10 requests/minute per IP**.

```bash
curl http://localhost:8000/health
```

---

## Configuration

All settings use the `CONTEXTCRAFT_` prefix. Full list in `.env.example`.

| Variable | Default | Description |
|---|---|---|
| `CONTEXTCRAFT_DATABASE_URL` | `postgresql://contextcraft:…@localhost:5432/contextcraft` | Postgres connection string |
| `CONTEXTCRAFT_GEMINI_API_KEY` | — | Gemini embeddings + LLM (default provider) |
| `CONTEXTCRAFT_GEMINI_MODEL` | `gemini-3.1-flash-lite` | Gemini LLM model |
| `CONTEXTCRAFT_EMBEDDING_PROVIDER` | `gemini` | `gemini` or `openai` |
| `CONTEXTCRAFT_LLM_PROVIDER` | `gemini` | `gemini`, `openai`, `anthropic`, `ollama` |
| `CONTEXTCRAFT_OPENAI_API_KEY` | — | Required when using OpenAI provider |
| `CONTEXTCRAFT_COHERE_API_KEY` | — | Enables Cohere reranking |
| `CONTEXTCRAFT_RERANK_ENABLED` | `true` | Toggle reranker on/off |
| `CONTEXTCRAFT_OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama endpoint |
| `CONTEXTCRAFT_OLLAMA_MODEL` | `qwen2.5-coder:7b` | Ollama model for local inference |
| `CONTEXTCRAFT_OLLAMA_ALLOW_REMOTE` | `false` | Allow non-localhost Ollama URLs |
| `CONTEXTCRAFT_ALLOWED_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | CORS origins (comma-separated) |
| `CONTEXTCRAFT_SEARCH_TOP_K` | `10` | Chunks returned after search/rerank |
| `CONTEXTCRAFT_API_PORT` | `8000` | API listen port |

### Alternative providers

**OpenAI** (embeddings + LLM):

```env
CONTEXTCRAFT_EMBEDDING_PROVIDER=openai
CONTEXTCRAFT_LLM_PROVIDER=openai
CONTEXTCRAFT_OPENAI_API_KEY=sk-...
```

**Ollama** (fully local, no API keys):

```bash
ollama serve
ollama pull qwen2.5-coder:7b
```

```env
CONTEXTCRAFT_LLM_PROVIDER=ollama
CONTEXTCRAFT_OLLAMA_MODEL=qwen2.5-coder:7b
```

Ollama is restricted to `localhost` by default. Set
`CONTEXTCRAFT_OLLAMA_ALLOW_REMOTE=true` only if you understand the SSRF risk.

---

## Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  tree-sitter │────▶│   CodeChunks     │────▶│    pgvector     │
│  AST parse   │     │  + git blame     │     │  PostgreSQL     │
└──────────────┘     └────────┬─────────┘     └────────┬────────┘
                               │                        │
                      ┌────────▼─────────┐              │
                      │   chunk_edges    │              │
                      │  (imports /      │              │
                      │   inherits)      │              │
                      └────────┬─────────┘              │
                               │                        │
                      ┌────────▼─────────┐    ┌─────────▼───────┐
                      │   Hybrid RRF     │◀───│  Vector + BM25  │
                      │  (per-repo norm) │    └─────────────────┘
                      └────────┬─────────┘
                               │
                      ┌────────▼─────────┐
                      │  Cohere rerank   │  (optional)
                      └────────┬─────────┘
                               │
                      ┌────────▼─────────┐     ┌──────────────┐
                      │  Context + LLM   │────▶│  Next.js UI  │
                      │  (SSE stream)    │     │  CLI         │
                      └──────────────────┘     └──────────────┘
```

**Design decisions**

- AST chunking at function and class boundaries preserves semantic units — the LLM
  never receives partial functions or broken syntax.
- Single PostgreSQL instance serves metadata, vectors (pgvector), and full-text
  search (tsvector) — no separate vector database service required.
- Per-repo RRF normalization prevents large codebases from crowding out smaller ones
  in multi-repo queries.
- Git blame runs once per file (not per chunk) via async subprocess — blame metadata
  adds negligible indexing overhead.
- Dependency expansion uses a single batched SQL query with a visited-set cycle guard
  — safe on codebases with circular imports.

---

## Supported languages

| Language | Extensions |
|---|---|
| Python | `.py` |
| JavaScript | `.js`, `.jsx` |
| TypeScript | `.ts`, `.tsx` |
| Go | `.go` |

ContextCraft pins `tree-sitter<0.22.0` for compatibility with `tree-sitter-languages`.
Additional languages can be added via the `LanguageAdapter` interface in
`src/contextcraft/parser/ast_parser.py`.

---

## Evaluation

```bash
python eval/run_eval.py --runs 3
python eval/run_eval.py --rerank --runs 3
python eval/run_eval.py --rerank --deps --runs 3
```

Measures source hit rate (does the right file appear?), faithfulness (does the
answer cover the ground truth?), and retrieval latency (P50/P95). Full results
and methodology: [BENCHMARK.md](BENCHMARK.md).

---

## Development

CI requires all four checks to pass before merge:

```bash
ruff format --check src/ tests/
ruff check src/ tests/
mypy src/contextcraft/ --strict
pytest tests/ -v --tb=short
```

To auto-fix formatting and lint:

```bash
ruff format src/ tests/
ruff check --fix src/ tests/
```

---

## Project structure

```
contextcraft/
├── src/contextcraft/
│   ├── cli/main.py           # Typer CLI — index, ask, status
│   ├── api/main.py           # FastAPI + SSE + rate limiting
│   ├── parser/ast_parser.py  # tree-sitter → CodeChunk
│   ├── graph/                # Import resolver + 1-hop expander
│   ├── embeddings/           # Gemini, OpenAI, Ollama embedders
│   ├── git/                  # Async blame + commit history
│   ├── db/                   # asyncpg pool + SQL migrations
│   ├── search/               # Vector, BM25, hybrid RRF
│   ├── reranker/             # Cohere cross-encoder
│   ├── llm/                  # Gemini, OpenAI, Anthropic, Ollama
│   ├── security.py           # Path traversal + query sanitization
│   └── startup.py            # API startup health checks
├── web/                      # Next.js 14 UI (App Router + SSE)
├── eval/                     # RAG evaluation harness + test cases
├── tests/                    # pytest unit tests
├── docker/
│   ├── Dockerfile            # Production image (non-root user)
│   └── docker-compose.yml    # PostgreSQL 16 + pgvector
├── railway.toml              # Railway deployment config
├── pyproject.toml
├── BENCHMARK.md              # Measured retrieval quality and latency
├── CHANGELOG.md
└── .env.example
```

---

## Deployment

### Railway (one click)

`railway.toml` is included. Set the following environment variables in the
Railway dashboard:

```
DATABASE_URL
CONTEXTCRAFT_GEMINI_API_KEY
CONTEXTCRAFT_COHERE_API_KEY        # optional
CONTEXTCRAFT_ALLOWED_ORIGINS       # set to your frontend URL
PORT                               # Railway sets this automatically
```

### Docker

```bash
docker build -f docker/Dockerfile -t contextcraft .
docker run -p 8000:8000 --env-file .env contextcraft
```

The production image runs as a non-root user and reads the port from `$PORT`.

> **Note:** A public hosted demo is not maintained to avoid uncontrolled API costs.
> The full stack runs locally with a free Gemini key — see Quick Start above.

---

## Roadmap

- [x] Phase 1: Core pipeline — tree-sitter parser, pgvector, hybrid RRF search
- [x] Phase 2: Cohere reranker, eval harness, Next.js web UI
- [x] Phase 3: Dependency graph, multi-repo search with per-repo RRF normalization
- [x] Phase 4: Eval benchmarks, PyPI publish (`pip install contextcraft-py`), Railway deploy
- [ ] Phase 5: File watcher for live re-indexing on save
- [ ] Phase 6: VS Code extension

---

## License

MIT