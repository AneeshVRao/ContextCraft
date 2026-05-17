"""Context builder: format search results into an LLM-ready prompt.

Takes the top-K ``SearchResult`` objects, fetches surrounding lines of
context, adds git blame metadata, and formats everything into a
structured string that fits within the token budget.
"""

from __future__ import annotations

import logging
from pathlib import Path

from contextcraft.config import settings
from contextcraft.models import SearchResult

logger = logging.getLogger(__name__)


def build_context(
    results: list[SearchResult],
    max_tokens: int | None = None,
    repo_path: str | None = None,
) -> str:
    """Build a prompt-ready context string from search results.

    Parameters
    ----------
    results:
        Ranked search results from hybrid search.
    max_tokens:
        Maximum token budget for the context block.  Defaults to
        ``settings.max_context_tokens``.
    repo_path:
        Absolute path to the repository root.  If provided and a file
        still exists on disk, surrounding context lines are included.

    Returns
    -------
    str
        Formatted context string with ``file_path:start_line`` headers.
    """
    max_tokens = max_tokens or settings.max_context_tokens
    sections: list[str] = []
    token_count = 0

    for sr in results:
        chunk = sr.chunk

        # Build the section header
        header = f"── {chunk.file_path}:{chunk.start_line}-{chunk.end_line}"
        header += f"  [{chunk.chunk_type.value}] {chunk.name}"
        if chunk.parent_name:
            header += f" (in {chunk.parent_name})"
        header += f"  (score: {sr.score:.4f})"

        # Build blame summary line
        blame_line = ""
        if chunk.git_blame:
            blame_line = (
                f"  Last modified by {chunk.git_blame.get('last_author', '?')} "
                f"on {chunk.git_blame.get('last_date', '?')} "
                f"({chunk.git_blame.get('last_commit', '?')})"
            )

        # Try to fetch surrounding context from disk
        surrounding = ""
        if repo_path:
            surrounding = _get_surrounding_lines(
                repo_path, chunk.file_path, chunk.start_line, chunk.end_line
            )

        # Build the full section
        content = chunk.content
        if surrounding:
            section = f"{header}\n{blame_line}\n{surrounding}\n"
        else:
            section = f"{header}\n{blame_line}\n```\n{content}\n```\n"

        # Token budget check (Pitfall 5)
        section_tokens = len(section) // 4  # rough estimate
        if token_count + section_tokens > max_tokens:
            logger.info(
                "Context budget exhausted at %d/%d tokens (%d chunks used)",
                token_count, max_tokens, len(sections),
            )
            break

        sections.append(section)
        token_count += section_tokens

    context = "\n".join(sections)

    # Add a summary footer
    footer = f"\n── {len(sections)} code chunks included ({token_count} estimated tokens)"
    return context + footer


def _get_surrounding_lines(
    repo_path: str,
    file_path: str,
    start_line: int,
    end_line: int,
    context_lines: int = 5,
) -> str:
    """Read the source file and return the chunk with ±context_lines of
    surrounding context, with line numbers."""
    full_path = Path(repo_path) / file_path
    if not full_path.is_file():
        return ""

    try:
        all_lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""

    # Calculate the range with padding
    ctx_start = max(0, start_line - 1 - context_lines)
    ctx_end = min(len(all_lines), end_line + context_lines)

    numbered_lines: list[str] = []
    for i in range(ctx_start, ctx_end):
        line_num = i + 1
        marker = "│" if start_line <= line_num <= end_line else "·"
        numbered_lines.append(f"{line_num:4d} {marker} {all_lines[i]}")

    return "```\n" + "\n".join(numbered_lines) + "\n```"


def format_sources(results: list[SearchResult]) -> str:
    """Format a compact source-reference block for display below LLM answers.

    This is shown as verified metadata, NOT from the LLM (Pitfall 8).
    """
    if not results:
        return ""

    lines: list[str] = ["Sources:"]
    for sr in results:
        c = sr.chunk
        entry = f"  • {c.file_path}:{c.start_line}-{c.end_line}"
        entry += f"  ({c.chunk_type.value}: {c.name})"
        if c.git_blame:
            entry += f"  by {c.git_blame.get('last_author', '?')}"
        lines.append(entry)

    return "\n".join(lines)
