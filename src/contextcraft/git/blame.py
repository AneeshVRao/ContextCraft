"""Per-file git blame parser.

Calls ``git blame --porcelain`` once per file (Pitfall 4 / Decision 5),
parses the output, and returns a mapping of line numbers to blame info.
The caller then slices out the relevant ranges for each code chunk.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from contextcraft.git.async_git import run_git

logger = logging.getLogger(__name__)


@dataclass
class LineBlame:
    """Blame information for a single source line."""

    line_num: int
    author: str
    commit_hash: str
    date: str


async def get_file_blame(repo_path: str | Path, file_path: str) -> dict[int, LineBlame]:
    """Run ``git blame --porcelain`` on *file_path* and return a dict
    mapping 1-indexed line numbers to ``LineBlame`` objects.

    Parameters
    ----------
    repo_path:
        Root of the git repository (used as ``cwd``).
    file_path:
        Path relative to *repo_path* of the file to blame.

    Returns
    -------
    dict[int, LineBlame]
        ``{line_number: LineBlame(…), …}``  Empty dict if blame fails.
    """
    try:
        returncode, stdout, _stderr = await run_git(
            ["blame", "--porcelain", file_path],
            cwd=str(repo_path),
            timeout=60.0,
        )
    except FileNotFoundError as exc:
        logger.warning("git blame failed for %s: %s", file_path, exc)
        return {}

    if returncode != 0:
        logger.debug("git blame returned %d for %s", returncode, file_path)
        return {}

    return _parse_porcelain(stdout)


def _parse_porcelain(output: str) -> dict[int, LineBlame]:
    """Parse ``git blame --porcelain`` output.

    Porcelain format:
      <40-char-hash> <orig-line> <final-line> [<num-lines>]
      author <name>
      author-mail <email>
      author-time <timestamp>
      author-tz <tz>
      committer <name>
      ...
      filename <path>
      \t<line-content>
    """
    blames: dict[int, LineBlame] = {}

    lines = output.split("\n")
    i = 0
    current_hash = ""
    current_line = 0
    current_author = ""
    current_date = ""

    while i < len(lines):
        line = lines[i]

        # Header line: <hash> <orig-line> <final-line> [<group-lines>]
        if len(line) >= 40 and line[0] not in ("\t", " ") and not line.startswith("author"):
            parts = line.split()
            if len(parts) >= 3:
                try:
                    current_hash = parts[0]
                    current_line = int(parts[2])  # final line number (1-indexed)
                except (ValueError, IndexError):
                    pass

        elif line.startswith("author "):
            current_author = line[len("author ") :]

        elif line.startswith("author-time "):
            # Unix timestamp — convert to ISO date
            try:
                import datetime

                ts = int(line[len("author-time ") :])
                current_date = datetime.datetime.fromtimestamp(ts, tz=datetime.UTC).strftime(
                    "%Y-%m-%d"
                )
            except (ValueError, OSError):
                current_date = ""

        elif line.startswith("\t"):
            # This is the actual source line — record the blame entry
            blames[current_line] = LineBlame(
                line_num=current_line,
                author=current_author,
                commit_hash=current_hash,
                date=current_date,
            )

        i += 1

    return blames


def get_chunk_blame(
    file_blame: dict[int, LineBlame],
    start_line: int,
    end_line: int,
) -> dict[str, object]:
    """Extract blame summary for a chunk's line range.

    Returns a dict with the most recent author and commit for the chunk.
    """
    chunk_blames = [b for line, b in file_blame.items() if start_line <= line <= end_line]
    if not chunk_blames:
        return {}

    # Find the most recent blame entry by date
    most_recent = max(chunk_blames, key=lambda b: b.date)
    # Collect unique authors
    authors = list({b.author for b in chunk_blames})

    return {
        "last_author": most_recent.author,
        "last_commit": most_recent.commit_hash[:12],
        "last_date": most_recent.date,
        "authors": authors,
        "line_count": len(chunk_blames),
    }
