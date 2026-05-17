# ContextCraft 🔍

> **CLI + API + Web UI that indexes any codebase with tree-sitter, stores semantic chunks in pgvector, reranks with Cohere, and answers engineering questions with full file + git-history context.**

[![CI](https://github.com/AneeshVRao/ContextCraft/actions/workflows/ci.yml/badge.svg)](https://github.com/AneeshVRao/ContextCraft/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## What it does

ContextCraft turns your codebase into a searchable knowledge base:

1. **Parses** your code with [tree-sitter](https://tree-sitter.github.io/) — extracts functions, classes, and modules as semantic chunks (not naive fixed-size splits)
2. **Builds a Graph** — Resolves Python imports and inheritance to understand cross-file dependencies
3. **Enriches** each chunk with git blame (who wrote it, when) and commit history
4. **Embeds** chunks with OpenAI `text-embedding-3-small` and stores them in PostgreSQL + pgvector
5. **Searches** using hybrid Reciprocal Rank Fusion (RRF) — combining vector similarity and full-text search across **multiple repositories**
6. **Reranks** top candidates with [Cohere](https://cohere.com/) cross-encoder (`rerank-english-v3.0`) for precision
7. **Answers** your questions with an LLM (OpenAI, Anthropic, or **local Ollama**), grounded in real code with file paths and line numbers
8. **Streams** answers via SSE to both the CLI and a sleek Next.js web interface

## Evaluation & Benchmarks
We don't just guess that the system works — we measure it. See [BENCHMARK.md](BENCHMARK.md) for hard numbers on our Reciprocal Rank Fusion (RRF), Cohere reranking, and Dependency Graph configurations, including **Source Hit Rate** and **P50/P95 Latency**.

## 60-Second Setup

### Prerequisites

- Python 3.11+
- Docker (for PostgreSQL + pgvector)
- An OpenAI API key
- _(Optional)_ A Cohere API key for reranking

### 1. Clone and install

```bash
git clone https://github.com/AneeshVRao/ContextCraft.git
cd contextcraft
pip install -e ".[dev]"
```

### 2. Start the database

```bash
docker compose -f docker/docker-compose.yml up -d
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env and set:
#   CONTEXTCRAFT_OPENAI_API_KEY=sk-...
#   CONTEXTCRAFT_COHERE_API_KEY=...  (optional, enables reranking)
```

### 4. Index a codebase

```bash
contextcraft index ./path/to/your/project
```

### 5. Ask questions

```bash
contextcraft ask "How does authentication work?"
contextcraft ask "What does the process_payment function do?"
contextcraft ask "Who last modified the database connection code?"

# Disable reranking for faster (but less precise) results
contextcraft ask "How does search work?" --no-rerank
```

## Web UI

ContextCraft includes a Next.js 14 web interface with real-time streaming, syntax-highlighted source citations, and repository selection.

```bash
cd web
npm install
npm run dev
# Open http://localhost:3000
```

Or run the full stack with Docker:

```bash
docker compose -f docker/docker-compose.yml up -d
```

## CLI Commands

### `contextcraft index <repo_path>`

Index a codebase: parse → git blame → embed → store.

```bash
# Full index
contextcraft index ./my-project

# Incremental (only changed files)
contextcraft index ./my-project --incremental

# Parse without embeddings (useful for testing)
contextcraft index ./my-project --skip-embeddings
```

### `contextcraft ask "question"`

Ask a question about indexed code. Streams the answer to your terminal.

```bash
# Basic query across all repos
contextcraft ask "Where is the authentication middleware?" --all-repos

# Query scoped to specific repos
contextcraft ask "How does the caching layer work?" --repos repo-a,repo-b

# Expand context with 1-hop dependencies
contextcraft ask "How do I instantiate the Database client?" --with-deps

# Use local models for privacy
CONTEXTCRAFT_LLM_PROVIDER=ollama contextcraft ask "Explain this function"
```

### `contextcraft status`

Show all indexed repositories with chunk counts and timestamps.

```bash
contextcraft status
```

## API

Start the API server:

```bash
uvicorn contextcraft.api.main:app --reload
```

### Endpoints

| Method | Path      | Description                         |
|--------|-----------|-------------------------------------|
| GET    | `/health` | Health check                        |
| GET    | `/repos`  | List indexed repositories           |
| POST   | `/index`  | Trigger indexing (background task)   |
| POST   | `/ask`    | Ask a question (SSE streaming)      |

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│  tree-sitter │────▶│  CodeChunks  │────▶│   pgvector    │
│   AST Parse  │     │  + git blame │     │  PostgreSQL   │
└─────────────┘     └──────────────┘     └───────┬───────┘
                                                  │
                    ┌──────────────┐               │
                    │  Hybrid RRF  │◀──────────────┘
                    │ Vector + BM25│
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │Cohere Rerank │
                    │ Cross-Encoder│
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐     ┌──────────────┐
                    │ Context Build │────▶│  Next.js UI  │
                    │  + LLM Call   │     │  (SSE stream) │
                    └──────────────┘     └──────────────┘
```

**Key decisions:**
- **AST chunking** over fixed-size: functions and classes are natural semantic units
- **pgvector** over Qdrant: same DB as metadata, SQL joins work natively
- **tsvector** over pg_bm25: zero dependencies, negligible difference after RRF
- **Per-file git blame**: one subprocess per file, not per chunk (50x speedup)
- **Cohere cross-encoder**: categorically better than bi-encoder for top-k precision
- **60-candidate pool**: fetch 60 from hybrid search, rerank down to requested top_k

## Supported Languages

| Language   | Extensions        |
|------------|-------------------|
| Python     | `.py`             |
| JavaScript | `.js`, `.jsx`     |
| TypeScript | `.ts`, `.tsx`     |
| Go         | `.go`             |

> **Note:** ContextCraft pins `tree-sitter<0.22.0` for compatibility with the
> `tree-sitter-languages` pre-compiled grammar package.  This means some
> bleeding-edge Go and TypeScript grammar features may not be fully
> supported.  We run explicit tests against Go structs with pointer-receiver
> methods and TypeScript interfaces to catch regressions.  See
> [tree-sitter-languages](https://github.com/grantjenks/py-tree-sitter-languages)
> for upstream status.

## Evaluation

ContextCraft includes a built-in evaluation harness to measure retrieval quality:

```bash
# Run evaluation without reranking
python eval/run_eval.py

# Run evaluation with Cohere reranking
python eval/run_eval.py --rerank
```

The harness measures source hit rate, LLM-as-a-judge faithfulness, and p50 latency across 10 benchmark queries. See [`eval/README.md`](eval/README.md) for details.

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/

# Type check
mypy src/contextcraft/
```

## Project Structure

```
contextcraft/
├── src/contextcraft/
│   ├── cli/main.py           # Typer CLI
│   ├── parser/ast_parser.py  # tree-sitter AST → CodeChunk
│   ├── embeddings/           # OpenAI + Ollama embedders
│   ├── git/                  # blame + commit history
│   ├── db/                   # asyncpg pool + CRUD
│   ├── search/               # vector, BM25, hybrid RRF
│   ├── reranker/             # Cohere cross-encoder reranking
│   ├── llm/                  # OpenAI + Anthropic providers
│   └── api/main.py           # FastAPI server
├── web/                      # Next.js 14 web UI
│   ├── src/app/              # App Router pages + API proxies
│   └── src/components/       # React components (chat, citations)
├── eval/                     # RAG evaluation harness
├── tests/
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── pyproject.toml
└── .env.example
```

## Roadmap

- [x] Phase 1: Core CLI — tree-sitter parser, pgvector, hybrid search, CLI
- [x] Phase 2: Cohere reranker, evaluation harness, Next.js web UI
- [ ] Phase 3: Cross-file dependency graph, multi-repo support, Ollama local LLM
- [ ] Phase 4: File watcher (live re-index), temporal queries, VSCode extension
- [ ] Phase 5: PyPI publish, blog post

## License

MIT
