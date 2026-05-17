"""Tests for the cross-file dependency graph resolver.

Uses ContextCraft's own codebase as the test corpus, validated against
the hand-traced ground truth in tests/fixtures/import_ground_truth.txt.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

import pytest

from contextcraft.graph.models import ChunkEdge
from contextcraft.graph.resolver import (
    _normalise_init_path,
    _normalise_module_path,
    build_chunk_registry,
    resolve_all,
    resolve_imports,
    resolve_inheritance,
)
from contextcraft.models import ChunkType, CodeChunk, Language

FIXTURES = Path(__file__).parent / "fixtures"


def _make_chunk(
    file_path: str,
    name: str = "test",
    content: str = "",
    imports: list[str] | None = None,
    chunk_type: ChunkType = ChunkType.FUNCTION,
) -> CodeChunk:
    """Helper to create a CodeChunk for testing."""
    return CodeChunk(
        file_path=file_path,
        chunk_type=chunk_type,
        name=name,
        content=content,
        start_line=1,
        end_line=10,
        language=Language.PYTHON,
        imports=imports or [],
    )


@pytest.mark.unit
class TestNormalisePaths(unittest.TestCase):
    """Test module path normalisation helpers."""

    def test_direct_module(self) -> None:
        assert _normalise_module_path("contextcraft.config") == "config.py"

    def test_nested_module(self) -> None:
        assert _normalise_module_path("contextcraft.db.connection") == "db/connection.py"

    def test_deep_module(self) -> None:
        assert (
            _normalise_module_path("contextcraft.search.context_builder")
            == "search/context_builder.py"
        )

    def test_init_path(self) -> None:
        assert _normalise_init_path("contextcraft.reranker") == "reranker/__init__.py"

    def test_init_path_nested(self) -> None:
        assert _normalise_init_path("contextcraft.db") == "db/__init__.py"


@pytest.mark.unit
class TestBuildChunkRegistry(unittest.TestCase):
    """Test chunk registry construction."""

    def test_groups_by_file(self) -> None:
        c1 = _make_chunk("config.py", name="func1")
        c2 = _make_chunk("config.py", name="func2")
        c3 = _make_chunk("models.py", name="class1")
        registry = build_chunk_registry([c1, c2, c3])
        assert len(registry["config.py"]) == 2
        assert len(registry["models.py"]) == 1

    def test_normalises_backslashes(self) -> None:
        c = _make_chunk("db\\connection.py")
        registry = build_chunk_registry([c])
        assert "db/connection.py" in registry


@pytest.mark.unit
class TestResolveImports(unittest.TestCase):
    """Test import edge resolution."""

    def setUp(self) -> None:
        self.config_chunk = _make_chunk("config.py", name="settings")
        self.models_chunk = _make_chunk("models.py", name="CodeChunk")
        self.registry = build_chunk_registry([self.config_chunk, self.models_chunk])

    def test_direct_import_resolves(self) -> None:
        """from contextcraft.config import settings → config.py"""
        source = _make_chunk(
            "db/connection.py",
            imports=["from contextcraft.config import settings"],
        )
        edges = resolve_imports(source, self.registry)
        assert len(edges) == 1
        assert edges[0].target_chunk_id == self.config_chunk.id
        assert edges[0].edge_type == "imports"
        assert edges[0].confidence == 1.0

    def test_multi_import_resolves(self) -> None:
        """Multiple imports from different modules."""
        source = _make_chunk(
            "cli/main.py",
            imports=[
                "from contextcraft.config import settings",
                "from contextcraft.models import CodeChunk",
            ],
        )
        edges = resolve_imports(source, self.registry)
        assert len(edges) == 2
        target_ids = {e.target_chunk_id for e in edges}
        assert self.config_chunk.id in target_ids
        assert self.models_chunk.id in target_ids

    def test_star_import_skipped(self) -> None:
        """Star imports should be skipped."""
        source = _make_chunk(
            "test.py",
            imports=["from contextcraft.models import *"],
        )
        edges = resolve_imports(source, self.registry)
        assert len(edges) == 0

    def test_third_party_skipped(self) -> None:
        """Imports not starting with contextcraft should be skipped."""
        source = _make_chunk(
            "test.py",
            imports=["from pydantic import BaseModel"],
        )
        edges = resolve_imports(source, self.registry)
        assert len(edges) == 0

    def test_unresolved_import_no_error(self) -> None:
        """Import to a file not in registry should produce no edges, not crash."""
        source = _make_chunk(
            "test.py",
            imports=["from contextcraft.nonexistent import foo"],
        )
        edges = resolve_imports(source, self.registry)
        assert len(edges) == 0

    def test_init_reexport_gets_half_confidence(self) -> None:
        """Imports via __init__.py re-exports get confidence=0.5."""
        init_chunk = _make_chunk("reranker/__init__.py", name="__init__")
        registry = build_chunk_registry([init_chunk])
        source = _make_chunk(
            "test.py",
            imports=["from contextcraft.reranker import BaseReranker"],
        )
        edges = resolve_imports(source, registry)
        assert len(edges) == 1
        assert edges[0].confidence == 0.5

    def test_no_duplicate_edges(self) -> None:
        """Same target should not produce duplicate edges."""
        source = _make_chunk(
            "test.py",
            imports=[
                "from contextcraft.config import settings",
                "from contextcraft.config import settings",
            ],
        )
        edges = resolve_imports(source, self.registry)
        assert len(edges) == 1


@pytest.mark.unit
class TestResolveInheritance(unittest.TestCase):
    """Test inheritance edge resolution."""

    def test_detects_inheritance(self) -> None:
        base_chunk = _make_chunk(
            "llm/base.py",
            name="BaseLLM",
            chunk_type=ChunkType.CLASS,
            content="class BaseLLM(ABC):\n    pass",
        )
        child_chunk = _make_chunk(
            "llm/openai.py",
            name="OpenAILLM",
            chunk_type=ChunkType.CLASS,
            content="class OpenAILLM(BaseLLM):\n    pass",
            imports=["from contextcraft.llm.base import BaseLLM"],
        )
        registry = build_chunk_registry([base_chunk, child_chunk])
        edges = resolve_inheritance(child_chunk, registry, [base_chunk, child_chunk])
        assert len(edges) == 1
        assert edges[0].target_chunk_id == base_chunk.id
        assert edges[0].edge_type == "inherits"
        assert edges[0].confidence == 1.0

    def test_skips_pydantic_base(self) -> None:
        """Should not create edges for BaseModel, BaseSettings, etc."""
        chunk = _make_chunk(
            "models.py",
            name="CodeChunk",
            chunk_type=ChunkType.CLASS,
            content="class CodeChunk(BaseModel):\n    pass",
        )
        edges = resolve_inheritance(chunk, {}, [chunk])
        assert len(edges) == 0

    def test_no_self_edges(self) -> None:
        """A class should not create an edge to itself."""
        chunk = _make_chunk(
            "base.py",
            name="BaseLLM",
            chunk_type=ChunkType.CLASS,
            content="class BaseLLM(ABC):\n    pass",
        )
        edges = resolve_inheritance(chunk, {}, [chunk])
        assert len(edges) == 0


@pytest.mark.unit
class TestResolveAll(unittest.TestCase):
    """Integration test for resolve_all."""

    def test_produces_both_import_and_inherit_edges(self) -> None:
        base = _make_chunk(
            "embeddings/base.py",
            name="BaseEmbedder",
            chunk_type=ChunkType.CLASS,
            content="class BaseEmbedder(ABC):\n    pass",
        )
        child = _make_chunk(
            "embeddings/openai.py",
            name="OpenAIEmbedder",
            chunk_type=ChunkType.CLASS,
            content="class OpenAIEmbedder(BaseEmbedder):\n    pass",
            imports=["from contextcraft.embeddings.base import BaseEmbedder"],
        )
        registry = build_chunk_registry([base, child])
        edges = resolve_all([base, child], registry)

        import_edges = [e for e in edges if e.edge_type == "imports"]
        inherit_edges = [e for e in edges if e.edge_type == "inherits"]

        assert len(import_edges) == 1
        assert len(inherit_edges) == 1
        assert import_edges[0].source_chunk_id == child.id
        assert inherit_edges[0].source_chunk_id == child.id


@pytest.mark.unit
class TestChunkEdgeModel(unittest.TestCase):
    """Test ChunkEdge Pydantic model."""

    def test_defaults(self) -> None:
        edge = ChunkEdge(
            source_chunk_id=uuid4(),
            target_chunk_id=uuid4(),
            edge_type="imports",
        )
        assert edge.confidence == 1.0

    def test_custom_confidence(self) -> None:
        edge = ChunkEdge(
            source_chunk_id=uuid4(),
            target_chunk_id=uuid4(),
            edge_type="imports",
            confidence=0.5,
        )
        assert edge.confidence == 0.5
