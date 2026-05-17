"""Git commit history per file.

Retrieves the last N commits that touched a given file, including
commit hash, message, author, and date.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from contextcraft.models import CommitInfo

logger = logging.getLogger(__name__)

DEFAULT_COMMIT_COUNT = 5


def get_file_history(
    repo_path: str | Path,
    file_path: str,
    max_commits: int = DEFAULT_COMMIT_COUNT,
) -> list[CommitInfo]:
    """Return the last *max_commits* commits that touched *file_path*.

    Parameters
    ----------
    repo_path:
        Root of the git repository.
    file_path:
        Path relative to *repo_path*.
    max_commits:
        Maximum number of commits to return.

    Returns
    -------
    list[CommitInfo]
        Most-recent-first list of commit summaries.
    """
    # Use a custom format separator that's unlikely to appear in commit messages
    sep = "<<SEP>>"
    fmt = f"%H{sep}%s{sep}%an{sep}%ai"

    try:
        result = subprocess.run(
            [
                "git", "log",
                f"-n{max_commits}",
                f"--pretty=format:{fmt}",
                "--", file_path,
            ],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning("git log failed for %s: %s", file_path, exc)
        return []

    if result.returncode != 0 or not result.stdout.strip():
        return []

    commits: list[CommitInfo] = []
    for line in result.stdout.strip().split("\n"):
        parts = line.split(sep)
        if len(parts) >= 4:
            commits.append(
                CommitInfo(
                    hash=parts[0][:12],
                    message=parts[1].strip(),
                    author=parts[2].strip(),
                    date=parts[3].strip(),
                )
            )

    return commits
