"""Security helpers: path validation, query sanitization, Ollama URL policy."""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

MAX_QUERY_LENGTH = 500

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_query(query: str) -> str:
    """Strip null bytes and control characters; cap length before LLM use."""
    cleaned = _CONTROL_CHAR_RE.sub("", query)
    if len(cleaned) > MAX_QUERY_LENGTH:
        cleaned = cleaned[:MAX_QUERY_LENGTH]
    return cleaned.strip()


def _sensitive_roots() -> list[Path]:
    """Directories that must never be indexed."""
    roots: list[Path] = []
    home = Path.home()
    for name in (".ssh", ".aws", ".gnupg", ".config"):
        candidate = home / name
        if candidate.exists():
            roots.append(candidate.resolve())

    for posix in ("/etc", "/var/run/secrets", "/root"):
        p = Path(posix)
        if p.exists():
            roots.append(p.resolve())

    # Windows system paths
    for win in (r"C:\Windows\System32\config", r"C:\Users\Default"):
        p = Path(win)
        if p.exists():
            roots.append(p.resolve())

    return roots


def validate_repo_path(repo_path: Path) -> Path:
    """Resolve *repo_path* and reject sensitive or invalid targets."""
    resolved = repo_path.expanduser().resolve()
    if not resolved.exists():
        msg = f"Path does not exist: {resolved}"
        raise ValueError(msg)
    if not resolved.is_dir():
        msg = f"Not a directory: {resolved}"
        raise ValueError(msg)

    for sensitive in _sensitive_roots():
        if resolved == sensitive or resolved.is_relative_to(sensitive):
            msg = f"Refusing to index sensitive directory: {resolved}"
            raise ValueError(msg)

    return resolved


def is_inside_repo(path: Path, repo_root: Path) -> bool:
    """Return True if *path* resolves to a location under *repo_root*."""
    try:
        path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False
    return True


def validate_ollama_base_url(url: str, *, allow_remote: bool) -> str:
    """Restrict Ollama to localhost by default (SSRF mitigation).

    Set ``CONTEXTCRAFT_OLLAMA_ALLOW_REMOTE=true`` to permit custom hosts.
    Custom hosts can reach internal network services — use only in trusted
    deployments.
    """
    normalized = url.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in ("http", "https"):
        msg = "Ollama base URL must use http or https"
        raise ValueError(msg)

    host = (parsed.hostname or "").lower()
    allowed = {"localhost", "127.0.0.1", "::1"}
    remote_ok = allow_remote or os.environ.get("CONTEXTCRAFT_OLLAMA_ALLOW_REMOTE", "").lower() in (
        "1",
        "true",
        "yes",
    )

    if host not in allowed and not remote_ok:
        msg = (
            f"Ollama URL host '{host}' is not localhost. "
            "Only http://localhost or http://127.0.0.1 are allowed by default "
            "(SSRF protection). Set CONTEXTCRAFT_OLLAMA_ALLOW_REMOTE=true to allow "
            "custom hosts — this exposes internal network endpoints to SSRF risk."
        )
        raise ValueError(msg)

    return normalized
