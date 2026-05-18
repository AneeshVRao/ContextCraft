"""Async subprocess wrappers for git commands."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def run_git(
    args: list[str],
    *,
    cwd: str,
    timeout: float,
) -> tuple[int, str, str]:
    """Run a git subprocess without blocking the event loop."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        logger.warning("git %s timed out after %ss in %s", args, timeout, cwd)
        return 1, "", "timeout"

    stdout = stdout_b.decode(errors="replace")
    stderr = stderr_b.decode(errors="replace")
    return proc.returncode or 0, stdout, stderr
