"""Tree-sitter AST parser for extracting semantic code chunks.

Loads a tree-sitter grammar for the detected language, walks the AST,
and yields ``CodeChunk`` objects for every function, class, or module-level
block found in the file.

Supported languages: Python, JavaScript/TypeScript, Go.
"""

from __future__ import annotations

import logging
from pathlib import Path

import tree_sitter_languages

from contextcraft.models import (
    EXTENSION_LANGUAGE_MAP,
    LANGUAGE_GRAMMAR_MAP,
    ChunkType,
    CodeChunk,
    Language,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AST node types we care about, per language
# ---------------------------------------------------------------------------
FUNCTION_NODE_TYPES: dict[Language, set[str]] = {
    Language.PYTHON: {"function_definition"},
    Language.JAVASCRIPT: {"function_declaration", "arrow_function", "method_definition"},
    Language.TYPESCRIPT: {"function_declaration", "arrow_function", "method_definition"},
    Language.GO: {"function_declaration", "method_declaration"},
}

CLASS_NODE_TYPES: dict[Language, set[str]] = {
    Language.PYTHON: {"class_definition"},
    Language.JAVASCRIPT: {"class_declaration"},
    Language.TYPESCRIPT: {"class_declaration"},
    Language.GO: set(),  # Go has no classes
}

# Node types whose children contain the entity's *name*
NAME_FIELD: dict[Language, str] = {
    Language.PYTHON: "name",
    Language.JAVASCRIPT: "name",
    Language.TYPESCRIPT: "name",
    Language.GO: "name",
}


def detect_language(file_path: str | Path) -> Language | None:
    """Return the ``Language`` for *file_path* based on its extension, or
    ``None`` if the extension is not recognised."""
    ext = Path(file_path).suffix.lower()
    return EXTENSION_LANGUAGE_MAP.get(ext)


def _get_parser(language: Language):
    """Return a tree-sitter ``Parser`` configured for *language*."""
    grammar_name = LANGUAGE_GRAMMAR_MAP[language]
    parser = tree_sitter_languages.get_parser(grammar_name)
    return parser


def _get_ts_language(language: Language):
    """Return the tree-sitter ``Language`` object for *language*."""
    grammar_name = LANGUAGE_GRAMMAR_MAP[language]
    return tree_sitter_languages.get_language(grammar_name)


def _node_name(node, language: Language) -> str:
    """Extract the identifier name from an AST node.

    Falls back to a positional description if no name field is found.
    """
    # Try the canonical "name" field first
    name_node = node.child_by_field_name(NAME_FIELD.get(language, "name"))
    if name_node is not None:
        return name_node.text.decode("utf-8")

    # For arrow functions assigned to a variable: const foo = () => { ... }
    if node.type in ("arrow_function",) and node.parent is not None:
        parent = node.parent
        if parent.type in ("variable_declarator", "lexical_declaration"):
            id_node = parent.child_by_field_name("name")
            if id_node is not None:
                return id_node.text.decode("utf-8")

    return f"<anonymous@{node.start_point[0] + 1}>"


def _node_text(node, source_bytes: bytes) -> str:
    """Return the source text covered by *node*."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _extract_imports_python(root_node, source_bytes: bytes) -> list[str]:
    """Pull top-level import names from a Python AST."""
    imports: list[str] = []
    for child in root_node.children:
        if child.type in ("import_statement", "import_from_statement"):
            imports.append(
                source_bytes[child.start_byte:child.end_byte].decode("utf-8").strip()
            )
    return imports


def _extract_docstring_python(node, source_bytes: bytes) -> str | None:
    """Return the docstring of a Python function/class if present."""
    body = node.child_by_field_name("body")
    if body is None:
        return None
    for child in body.children:
        if child.type == "expression_statement":
            for sub in child.children:
                if sub.type == "string":
                    return sub.text.decode("utf-8")
        break  # only check the first statement
    return None


def _find_parent_class(node) -> str | None:
    """Walk up the tree to find the enclosing class name, if any."""
    current = node.parent
    while current is not None:
        if current.type in ("class_definition", "class_declaration"):
            name_node = current.child_by_field_name("name")
            if name_node is not None:
                return name_node.text.decode("utf-8")
        current = current.parent
    return None


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------


def parse_file(
    file_path: str | Path,
    language: Language | None = None,
    repo_root: str | Path | None = None,
) -> list[CodeChunk]:
    """Parse *file_path* and return a list of ``CodeChunk`` objects.

    Parameters
    ----------
    file_path:
        Absolute or relative path to the source file.
    language:
        Override language detection.  If ``None``, detected from file extension.
    repo_root:
        If provided, ``CodeChunk.file_path`` is stored relative to this root.

    Returns
    -------
    list[CodeChunk]
        One chunk per function / class / module-level block found.
    """
    file_path = Path(file_path)
    if language is None:
        language = detect_language(file_path)
    if language is None:
        logger.debug("Unsupported file extension: %s", file_path.suffix)
        return []

    source_bytes = file_path.read_bytes()
    if not source_bytes.strip():
        return []

    # Determine the relative path to store
    if repo_root is not None:
        try:
            rel_path = str(file_path.resolve().relative_to(Path(repo_root).resolve()))
        except ValueError:
            rel_path = str(file_path)
    else:
        rel_path = str(file_path)
    # Normalise to forward slashes for cross-platform consistency
    rel_path = rel_path.replace("\\", "/")

    parser = _get_parser(language)
    tree = parser.parse(source_bytes)
    root = tree.root_node

    chunks: list[CodeChunk] = []

    # Extract top-level imports (Python only for now)
    file_imports: list[str] = []
    if language == Language.PYTHON:
        file_imports = _extract_imports_python(root, source_bytes)

    # Walk the AST
    _walk_node(
        node=root,
        source_bytes=source_bytes,
        language=language,
        rel_path=rel_path,
        file_imports=file_imports,
        chunks=chunks,
    )

    # If we found no function/class chunks, emit a single module-level chunk
    if not chunks and source_bytes.strip():
        chunks.append(
            CodeChunk(
                file_path=rel_path,
                chunk_type=ChunkType.MODULE,
                name=Path(file_path).stem,
                content=source_bytes.decode("utf-8", errors="replace"),
                start_line=1,
                end_line=source_bytes.count(b"\n") + 1,
                language=language,
                imports=file_imports,
            )
        )

    # Safety check per Pitfall 1
    if not chunks:
        logger.warning(
            "Parser returned 0 chunks for non-empty file %s — possible grammar issue",
            file_path,
        )

    return chunks


def _walk_node(
    node,
    source_bytes: bytes,
    language: Language,
    rel_path: str,
    file_imports: list[str],
    chunks: list[CodeChunk],
    *,
    _depth: int = 0,
) -> None:
    """Recursively walk the AST and collect chunks for functions and classes."""
    func_types = FUNCTION_NODE_TYPES.get(language, set())
    class_types = CLASS_NODE_TYPES.get(language, set())

    if node.type in func_types:
        name = _node_name(node, language)
        parent_class = _find_parent_class(node)
        content = _node_text(node, source_bytes)
        start_line = node.start_point[0] + 1  # 1-indexed
        end_line = node.end_point[0] + 1

        chunks.append(
            CodeChunk(
                file_path=rel_path,
                chunk_type=ChunkType.FUNCTION,
                name=name,
                parent_name=parent_class,
                content=content,
                start_line=start_line,
                end_line=end_line,
                language=language,
                imports=file_imports,
            )
        )
        # Don't recurse into nested functions — they'll be their own chunks
        # if they're top-level enough; otherwise they stay part of the parent.
        return

    if node.type in class_types:
        name = _node_name(node, language)
        content = _node_text(node, source_bytes)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        # Emit the class as a whole chunk
        chunks.append(
            CodeChunk(
                file_path=rel_path,
                chunk_type=ChunkType.CLASS,
                name=name,
                content=content,
                start_line=start_line,
                end_line=end_line,
                language=language,
                imports=file_imports,
            )
        )

        # Also recurse into the class body to emit individual methods
        for child in node.children:
            _walk_node(
                child,
                source_bytes,
                language,
                rel_path,
                file_imports,
                chunks,
                _depth=_depth + 1,
            )
        return

    # For other node types, just recurse
    for child in node.children:
        _walk_node(
            child,
            source_bytes,
            language,
            rel_path,
            file_imports,
            chunks,
            _depth=_depth + 1,
        )
