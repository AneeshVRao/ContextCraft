-- Migration 003: chunk_edges table for cross-file dependency graph
--
-- Stores import and inheritance edges between code chunks.
-- Used by the context expander to pull in dependency chunks.

CREATE TABLE IF NOT EXISTS chunk_edges (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_chunk_id UUID NOT NULL REFERENCES code_chunks(id) ON DELETE CASCADE,
    target_chunk_id UUID NOT NULL REFERENCES code_chunks(id) ON DELETE CASCADE,
    edge_type       TEXT NOT NULL,       -- 'imports' or 'inherits'
    confidence      FLOAT NOT NULL DEFAULT 1.0,
    UNIQUE(source_chunk_id, target_chunk_id, edge_type)
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON chunk_edges(source_chunk_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON chunk_edges(target_chunk_id);
