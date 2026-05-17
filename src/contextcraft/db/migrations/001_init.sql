-- ContextCraft: initial database schema
-- Requires: PostgreSQL 16+ with pgvector and pg_trgm extensions

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------------
-- repositories
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS repositories (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    local_path      TEXT UNIQUE NOT NULL,
    language        TEXT[] NOT NULL DEFAULT '{}',
    last_indexed_at TIMESTAMPTZ,
    last_commit_hash TEXT,
    chunk_count     INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- code_chunks
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS code_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    file_path       TEXT NOT NULL,
    chunk_type      TEXT NOT NULL,
    name            TEXT NOT NULL,
    parent_name     TEXT,
    content         TEXT NOT NULL,
    start_line      INT NOT NULL,
    end_line        INT NOT NULL,
    embedding       VECTOR(1536),
    content_hash    TEXT NOT NULL,
    git_blame       JSONB DEFAULT '{}',
    commit_history  JSONB DEFAULT '[]',
    imports         TEXT[] DEFAULT '{}',
    language        TEXT NOT NULL,
    indexed_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_chunks_repo     ON code_chunks(repo_id);
CREATE INDEX IF NOT EXISTS idx_chunks_file     ON code_chunks(repo_id, file_path);
CREATE INDEX IF NOT EXISTS idx_chunks_hash     ON code_chunks(content_hash);
CREATE INDEX IF NOT EXISTS idx_chunks_fts      ON code_chunks USING gin(to_tsvector('english', content));

-- NOTE: HNSW index should be created AFTER bulk insert for performance.
-- Run manually:
--   CREATE INDEX CONCURRENTLY idx_chunks_embedding
--   ON code_chunks USING hnsw (embedding vector_cosine_ops)
--   WITH (m = 16, ef_construction = 64);
