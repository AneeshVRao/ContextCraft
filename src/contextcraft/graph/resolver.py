"""Import resolver — maps code chunk imports to chunk IDs in the database.

Resolves static, absolute imports within the indexed repository only.

Handles:
- Direct imports: ``from contextcraft.config import settings`` → confidence=1.0
- ``__init__.py`` re-exports: ``from contextcraft import settings`` → confidence=0.5

Skips:
- Star imports (``from x import *``)
- Conditional imports (``try: ... except ImportError: ...``)
- Dynamic imports (``importlib.import_module(...)``)
- Third-party packages (not in chunk_registry)
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

from contextcraft.graph.models import ChunkEdge
from contextcraft.models import CodeChunk

logger = logging.getLogger(__name__)


def _normalise_module_path(module: str) -> str:
    """Convert a dotted module path to a file-like path.

    ``contextcraft.db.connection`` → ``db/connection.py``
    ``contextcraft.models`` → ``models.py``
    """
    # Strip the top-level package name (contextcraft.)
    parts = module.split(".")
    if parts and parts[0] == "contextcraft":
        parts = parts[1:]
    if not parts:
        return ""
    return "/".join(parts) + ".py"


def _normalise_init_path(module: str) -> str:
    """Convert a dotted module path to an ``__init__.py`` path.

    ``contextcraft.reranker`` → ``reranker/__init__.py``
    """
    parts = module.split(".")
    if parts and parts[0] == "contextcraft":
        parts = parts[1:]
    if not parts:
        return ""
    return "/".join(parts) + "/__init__.py"


def build_chunk_registry(
    chunks: list[CodeChunk],
) -> dict[str, list[UUID]]:
    """Build a mapping from normalised file paths to chunk IDs.

    A single file may contain multiple chunks (functions, classes).
    The registry maps ``"db/connection.py"`` → ``[uuid1, uuid2, ...]``.
    """
    registry: dict[str, list[UUID]] = {}
    for chunk in chunks:
        # Normalise backslashes to forward slashes
        path = chunk.file_path.replace("\\", "/")
        registry.setdefault(path, []).append(chunk.id)
    return registry


# Regex to match `from <module> import <names>` statements
_FROM_IMPORT_RE = re.compile(
    r"^from\s+(contextcraft(?:\.\w+)*)\s+import\s+(.+)$",
    re.MULTILINE,
)

# Regex to match `from contextcraft.<pkg> import <module>` (package-level)
_PACKAGE_IMPORT_RE = re.compile(
    r"^from\s+(contextcraft(?:\.\w+)*)\s+import\s+(\w+)",
    re.MULTILINE,
)


def resolve_imports(
    chunk: CodeChunk,
    chunk_registry: dict[str, list[UUID]],
) -> list[ChunkEdge]:
    """Resolve static, absolute imports within the indexed repository.

    Parameters
    ----------
    chunk:
        The source chunk whose imports we are resolving.
    chunk_registry:
        Mapping from normalised file paths (e.g. ``"db/connection.py"``)
        to lists of chunk UUIDs in that file.

    Returns
    -------
    list[ChunkEdge]
        Edges from this chunk to every resolvable target chunk.
    """
    edges: list[ChunkEdge] = []
    seen: set[tuple[UUID, str]] = set()  # (target_id, edge_type) dedup

    for imp in chunk.imports:
        # Skip star imports
        if "import *" in imp:
            logger.debug("Skipping star import: %s", imp)
            continue

        match = _FROM_IMPORT_RE.match(imp)
        if not match:
            continue

        module = match.group(1)
        # names = match.group(2)  # not needed for file-level resolution

        # Try direct module path: from contextcraft.db.connection import get_pool
        # → target file is db/connection.py
        target_path = _normalise_module_path(module)

        if target_path in chunk_registry:
            for target_id in chunk_registry[target_path]:
                key = (target_id, "imports")
                if key not in seen:
                    seen.add(key)
                    edges.append(
                        ChunkEdge(
                            source_chunk_id=chunk.id,
                            target_chunk_id=target_id,
                            edge_type="imports",
                            confidence=1.0,
                        )
                    )
        else:
            # Try __init__.py re-export:
            # from contextcraft.reranker import BaseReranker
            # → reranker/__init__.py re-exports from reranker/base.py
            init_path = _normalise_init_path(module)
            if init_path in chunk_registry:
                for target_id in chunk_registry[init_path]:
                    key = (target_id, "imports")
                    if key not in seen:
                        seen.add(key)
                        edges.append(
                            ChunkEdge(
                                source_chunk_id=chunk.id,
                                target_chunk_id=target_id,
                                edge_type="imports",
                                confidence=0.5,
                            )
                        )
            else:
                logger.debug(
                    "Unresolved import in %s: %s (tried %s and %s)",
                    chunk.file_path,
                    imp,
                    target_path,
                    init_path,
                )

    return edges


def resolve_inheritance(
    chunk: CodeChunk,
    chunk_registry: dict[str, list[UUID]],
    all_chunks: list[CodeChunk],
) -> list[ChunkEdge]:
    """Detect class inheritance edges.

    Scans the chunk's content for ``class Foo(Bar):`` patterns where
    ``Bar`` is a class defined in another file that was imported.

    Parameters
    ----------
    chunk:
        The source chunk to analyse.
    chunk_registry:
        File path → chunk ID mapping.
    all_chunks:
        All chunks in the repo (used to look up class names).

    Returns
    -------
    list[ChunkEdge]
        Inheritance edges with ``edge_type='inherits'``.
    """
    edges: list[ChunkEdge] = []

    # Build a name → chunk_id mapping for classes
    class_name_map: dict[str, list[UUID]] = {}
    for c in all_chunks:
        if c.chunk_type.value == "class":
            class_name_map.setdefault(c.name, []).append(c.id)

    # Find class definitions in this chunk that inherit from known classes
    class_pattern = re.compile(r"class\s+\w+\((\w+(?:,\s*\w+)*)\):")
    for match in class_pattern.finditer(chunk.content):
        bases = [b.strip() for b in match.group(1).split(",")]
        for base_name in bases:
            # Skip stdlib bases
            if base_name in (
                "BaseModel",
                "BaseSettings",
                "ABC",
                "Protocol",
                "Exception",
                "Enum",
                "str",
                "int",
                "object",
            ):
                continue
            if base_name in class_name_map:
                for target_id in class_name_map[base_name]:
                    # Don't create self-edges
                    if target_id != chunk.id:
                        edges.append(
                            ChunkEdge(
                                source_chunk_id=chunk.id,
                                target_chunk_id=target_id,
                                edge_type="inherits",
                                confidence=1.0,
                            )
                        )

    return edges


def resolve_all(
    chunks: list[CodeChunk],
    chunk_registry: dict[str, list[UUID]],
) -> list[ChunkEdge]:
    """Resolve all import and inheritance edges for a list of chunks.

    This is the main entry point — call once after indexing.
    """
    all_edges: list[ChunkEdge] = []
    for chunk in chunks:
        all_edges.extend(resolve_imports(chunk, chunk_registry))
        all_edges.extend(resolve_inheritance(chunk, chunk_registry, chunks))

    logger.info(
        "Resolved %d edges (%d imports, %d inherits)",
        len(all_edges),
        sum(1 for e in all_edges if e.edge_type == "imports"),
        sum(1 for e in all_edges if e.edge_type == "inherits"),
    )
    return all_edges
