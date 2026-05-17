# ContextCraft 🔍

> **CLI + API that indexes any codebase with tree-sitter, stores semantic chunks in pgvector, and answers engineering questions with full file + git-history context.**

[![CI](https://github.com/your-username/contextcraft/actions/workflows/ci.yml/badge.svg)](https://github.com/your-username/contextcraft/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## What it does

ContextCraft turns your codebase into a searchable knowledge base:

1. **Parses** your code with [tree-sitter](https://tree-sitter.github.io/) — extracts functions, classes, and modules as semantic chunks (not naive fixed-size splits)
2. **Enriches** each chunk with git blame (who wrote it, when) and commit history
3. **Embeds** chunks with OpenAI `text-embedding-3-small` and stores them in PostgreSQL + pgvector
4. **Searches** using hybrid Reciprocal Rank Fusion (RRF) — combining vector similarity and full-text search
5. **Answers** your questions with an LLM, grounded in real code with file paths and line numbers

## 60-Second Setup

### Prerequisites

- Python 3.11+
- Docker (for PostgreSQL + pgvector)
- An OpenAI API key

### 1. Clone and install

```bash
git clone https://github.com/your-username/contextcraft.git
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
# Edit .env and set your CONTEXTCRAFT_OPENAI_API_KEY
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
contextcraft ask "How does the user authentication flow work?"
contextcraft ask "What tests cover the payment module?" --repo my-project
contextcraft ask "Explain the database schema" --top-k 15
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
                    │ Context Build │
                    │  + LLM Call   │
                    └──────────────┘
```

**Key decisions:**
- **AST chunking** over fixed-size: functions and classes are natural semantic units
- **pgvector** over Qdrant: same DB as metadata, SQL joins work natively
- **tsvector** over pg_bm25: zero dependencies, negligible difference after RRF
- **Per-file git blame**: one subprocess per file, not per chunk (50x speedup)

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

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/ tests/

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
│   ├── llm/                  # OpenAI + Anthropic providers
│   └── api/main.py           # FastAPI server
├── tests/
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── pyproject.toml
└── .env.example
```

## Roadmap

- [x] Phase 1: Core CLI — tree-sitter parser, pgvector, hybrid search, CLI
- [ ] Phase 2: Cohere reranker, cross-file deps, web UI, file watcher
- [ ] Phase 3: Multi-repo, temporal queries, Ollama support, VSCode extension
- [ ] Phase 4: PyPI publish, blog post

## License

MIT
