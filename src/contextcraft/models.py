"""Pydantic models for ContextCraft.

Defines the core data structures used across the project:
- CodeChunk: a semantic unit extracted from source code via tree-sitter
- Repository: metadata about an indexed codebase
- SearchResult: a ranked chunk returned from hybrid search
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field


class ChunkType(str, Enum):
    """Type of code chunk extracted from AST."""

    FUNCTION = "function"
    CLASS = "class"
    MODULE = "module"
    PARTIAL = "partial"


class Language(str, Enum):
    """Supported programming languages."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"


# ---------------------------------------------------------------------------
# Map file extensions → Language enum
# ---------------------------------------------------------------------------
EXTENSION_LANGUAGE_MAP: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".js": Language.JAVASCRIPT,
    ".jsx": Language.JAVASCRIPT,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TYPESCRIPT,
    ".go": Language.GO,
}

# ---------------------------------------------------------------------------
# Map Language → tree-sitter grammar name
# ---------------------------------------------------------------------------
LANGUAGE_GRAMMAR_MAP: dict[Language, str] = {
    Language.PYTHON: "python",
    Language.JAVASCRIPT: "javascript",
    Language.TYPESCRIPT: "typescript",
    Language.GO: "go",
}


class LineBlame(BaseModel):
    """Git blame information for a single line."""

    line_num: int
    author: str
    commit_hash: str
    date: str


class CommitInfo(BaseModel):
    """Summary of a single git commit relevant to a file."""

    hash: str
    message: str
    author: str
    date: str


class CodeChunk(BaseModel):
    """A semantic code chunk extracted from tree-sitter AST.

    Represents a function, class, module-level block, or a partial split
    of a large function.  Carries git blame / history metadata and an
    optional embedding vector.
    """

    id: UUID = Field(default_factory=uuid4)
    repo_id: UUID | None = None
    file_path: str  # relative path, e.g. "src/auth/jwt.py"
    chunk_type: ChunkType
    name: str  # AST node name, e.g. "validate_token"
    parent_name: str | None = None  # class name if method, None if top-level
    content: str  # raw source code of the chunk
    start_line: int  # 1-indexed
    end_line: int
    language: Language
    imports: list[str] = Field(default_factory=list)

    # Optional fields populated during the pipeline
    embedding: list[float] | None = None
    git_blame: dict[str, object] = Field(default_factory=dict)
    commit_history: list[CommitInfo] = Field(default_factory=list)

    indexed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def content_hash(self) -> str:
        """SHA-256 hash of the raw content — used for incremental re-index."""
        return hashlib.sha256(self.content.encode()).hexdigest()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def token_estimate(self) -> int:
        """Rough token count (chars / 4).  Used for context-window budgeting."""
        return len(self.content) // 4


class Repository(BaseModel):
    """Metadata about an indexed repository."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    local_path: str
    languages: list[Language] = Field(default_factory=list)
    last_indexed_at: datetime | None = None
    last_commit_hash: str | None = None
    chunk_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SearchResult(BaseModel):
    """A code chunk returned from hybrid search, with relevance score."""

    chunk: CodeChunk
    score: float
    rank: int
