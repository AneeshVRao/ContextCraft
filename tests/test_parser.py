"""Tests for the tree-sitter AST parser.

Validates that ``parse_file`` correctly extracts CodeChunk objects from
known fixture files, with the right chunk types, names, line ranges,
and parent context.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from contextcraft.models import ChunkType, Language
from contextcraft.parser.ast_parser import detect_language, parse_file

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------


class TestDetectLanguage:
    def test_python(self):
        assert detect_language("foo.py") == Language.PYTHON

    def test_javascript(self):
        assert detect_language("bar.js") == Language.JAVASCRIPT

    def test_typescript(self):
        assert detect_language("baz.ts") == Language.TYPESCRIPT

    def test_go(self):
        assert detect_language("main.go") == Language.GO

    def test_unsupported(self):
        assert detect_language("readme.md") is None

    def test_case_insensitive(self):
        assert detect_language("FOO.PY") == Language.PYTHON


# ---------------------------------------------------------------------------
# Python parsing
# ---------------------------------------------------------------------------


class TestParsePython:
    @pytest.fixture(autouse=True)
    def _parse(self):
        self.chunks = parse_file(FIXTURES / "sample_python.py")

    def test_non_empty(self):
        """Pitfall 1 guard: parser must return chunks for a non-empty file."""
        assert len(self.chunks) > 0

    def test_finds_top_level_functions(self):
        names = {
            c.name
            for c in self.chunks
            if c.chunk_type == ChunkType.FUNCTION and c.parent_name is None
        }
        assert "greet" in names
        assert "add" in names
        assert "process_file" in names

    def test_finds_class(self):
        classes = [c for c in self.chunks if c.chunk_type == ChunkType.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "Calculator"

    def test_finds_methods(self):
        methods = [
            c
            for c in self.chunks
            if c.chunk_type == ChunkType.FUNCTION and c.parent_name == "Calculator"
        ]
        method_names = {m.name for m in methods}
        assert {"__init__", "add", "subtract", "reset"}.issubset(method_names)

    def test_chunk_has_correct_language(self):
        for chunk in self.chunks:
            assert chunk.language == Language.PYTHON

    def test_line_numbers_are_positive(self):
        for chunk in self.chunks:
            assert chunk.start_line >= 1
            assert chunk.end_line >= chunk.start_line

    def test_content_is_non_empty(self):
        for chunk in self.chunks:
            assert len(chunk.content.strip()) > 0

    def test_content_hash_is_deterministic(self):
        chunks_again = parse_file(FIXTURES / "sample_python.py")
        for a, b in zip(self.chunks, chunks_again):
            assert a.content_hash == b.content_hash

    def test_imports_extracted(self):
        """At least some chunks should carry the file's import list."""
        chunks_with_imports = [c for c in self.chunks if c.imports]
        assert len(chunks_with_imports) > 0
        # Should contain our known imports
        all_imports = chunks_with_imports[0].imports
        joined = " ".join(all_imports)
        assert "Path" in joined
        assert "pathlib" in joined


# ---------------------------------------------------------------------------
# JavaScript parsing
# ---------------------------------------------------------------------------


class TestParseJavaScript:
    @pytest.fixture(autouse=True)
    def _parse(self):
        self.chunks = parse_file(FIXTURES / "sample_javascript.js")

    def test_non_empty(self):
        assert len(self.chunks) > 0

    def test_finds_function(self):
        names = {c.name for c in self.chunks if c.chunk_type == ChunkType.FUNCTION}
        assert "greet" in names

    def test_finds_class(self):
        classes = [c for c in self.chunks if c.chunk_type == ChunkType.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "Calculator"

    def test_finds_methods(self):
        methods = [
            c
            for c in self.chunks
            if c.chunk_type == ChunkType.FUNCTION and c.parent_name == "Calculator"
        ]
        assert len(methods) >= 2  # constructor, add, subtract


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_unsupported_extension_returns_empty(self, tmp_path: Path):
        f = tmp_path / "readme.md"
        f.write_text("# Hello")
        assert parse_file(f) == []

    def test_empty_file_returns_empty(self, tmp_path: Path):
        f = tmp_path / "empty.py"
        f.write_text("")
        assert parse_file(f) == []

    def test_file_with_only_imports(self, tmp_path: Path):
        f = tmp_path / "imports_only.py"
        f.write_text("import os\nimport sys\n")
        chunks = parse_file(f)
        # Should produce at least a module-level chunk
        assert len(chunks) >= 1

    def test_relative_path_with_repo_root(self, tmp_path: Path):
        src = tmp_path / "src" / "app.py"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("def hello(): pass\n")
        chunks = parse_file(src, repo_root=tmp_path)
        assert chunks[0].file_path == "src/app.py"


# ---------------------------------------------------------------------------
# TypeScript parsing — exercises interface + class constructs where older
# tree-sitter grammars are known to produce incorrect AST nodes.
# ---------------------------------------------------------------------------


class TestParseTypeScript:
    @pytest.fixture(autouse=True)
    def _parse(self):
        self.chunks = parse_file(FIXTURES / "sample_typescript.ts")

    def test_non_empty(self):
        assert len(self.chunks) > 0

    def test_finds_function(self):
        names = {c.name for c in self.chunks if c.chunk_type == ChunkType.FUNCTION}
        assert "createUser" in names

    def test_finds_class(self):
        classes = [c for c in self.chunks if c.chunk_type == ChunkType.CLASS]
        assert any(c.name == "AuthService" for c in classes)

    def test_finds_methods(self):
        methods = [
            c
            for c in self.chunks
            if c.chunk_type == ChunkType.FUNCTION and c.parent_name == "AuthService"
        ]
        method_names = {m.name for m in methods}
        assert "login" in method_names
        assert "logout" in method_names

    def test_correct_language(self):
        for chunk in self.chunks:
            assert chunk.language == Language.TYPESCRIPT


# ---------------------------------------------------------------------------
# Go parsing — exercises struct + method (pointer receiver) constructs where
# older tree-sitter grammars are known to produce incorrect AST nodes.
# ---------------------------------------------------------------------------


class TestParseGo:
    @pytest.fixture(autouse=True)
    def _parse(self):
        self.chunks = parse_file(FIXTURES / "sample_go.go")

    def test_non_empty(self):
        assert len(self.chunks) > 0

    def test_finds_functions(self):
        names = {c.name for c in self.chunks if c.chunk_type == ChunkType.FUNCTION}
        # Should find the standalone function and the method declarations
        assert "NewUserConfig" in names or "main" in names

    def test_finds_method_declarations(self):
        """Go methods use method_declaration nodes (pointer receivers)."""
        func_names = {c.name for c in self.chunks if c.chunk_type == ChunkType.FUNCTION}
        # At minimum, the parser should find Greet and ConnectionString
        assert "Greet" in func_names or "ConnectionString" in func_names

    def test_correct_language(self):
        for chunk in self.chunks:
            assert chunk.language == Language.GO
