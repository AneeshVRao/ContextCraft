"""Pydantic models for the cross-file dependency graph."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ChunkEdge(BaseModel):
    """A directed edge between two code chunks.

    Represents an import or inheritance relationship discovered
    by static analysis of the AST.
    """

    source_chunk_id: UUID
    target_chunk_id: UUID
    edge_type: str = Field(description="'imports' or 'inherits'")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence in the edge. 1.0 for direct imports, 0.5 for __init__ re-exports."
        ),
    )
