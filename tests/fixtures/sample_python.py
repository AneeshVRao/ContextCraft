"""Sample Python module used as a test fixture for the AST parser.

This file contains a variety of constructs: imports, top-level functions,
a class with methods, and nested structures — all designed to exercise
the tree-sitter parser thoroughly.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Top-level function
# ---------------------------------------------------------------------------

def greet(name: str) -> str:
    """Return a greeting string."""
    return f"Hello, {name}!"


def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


# ---------------------------------------------------------------------------
# Class with methods
# ---------------------------------------------------------------------------

class Calculator:
    """A simple calculator class."""

    def __init__(self, initial: float = 0.0):
        self.value = initial

    def add(self, x: float) -> float:
        """Add *x* to the current value."""
        self.value += x
        return self.value

    def subtract(self, x: float) -> float:
        """Subtract *x* from the current value."""
        self.value -= x
        return self.value

    def reset(self) -> None:
        """Reset to zero."""
        self.value = 0.0


# ---------------------------------------------------------------------------
# Another top-level function
# ---------------------------------------------------------------------------

def process_file(path: str, encoding: str = "utf-8") -> str | None:
    """Read a file and return its content, or None on error."""
    try:
        return Path(path).read_text(encoding=encoding)
    except OSError:
        return None
