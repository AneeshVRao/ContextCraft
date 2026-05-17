"""Application settings loaded from environment variables.

Uses pydantic-settings so every value can be overridden via env vars
prefixed with ``CONTEXTCRAFT_``.  A ``.env`` file in the project root
is loaded automatically.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for ContextCraft."""

    model_config = SettingsConfigDict(
        env_prefix="CONTEXTCRAFT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database --------------------------------------------------------
    database_url: str = "postgresql://contextcraft:contextcraft@localhost:5432/contextcraft"

    db_min_connections: int = 2
    db_max_connections: int = 20  # sized for concurrent indexing + API serving

    # --- Embeddings ------------------------------------------------------
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 100
    embedding_max_concurrent: int = 5

    # --- LLM -------------------------------------------------------------
    llm_provider: str = "openai"  # "openai" | "anthropic"
    openai_chat_model: str = "gpt-4o"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # --- Search & Reranking ----------------------------------------------
    search_top_k: int = 10
    max_context_tokens: int = 20_000

    rerank_enabled: bool = True
    cohere_api_key: str = ""
    rerank_model: str = "rerank-english-v3.0"
    rerank_top_n: int = 8

    # --- Indexing --------------------------------------------------------
    max_chunk_tokens: int = 800
    default_ignore_patterns: list[str] = [
        "node_modules",
        ".git",
        "__pycache__",
        "*.pyc",
        "dist",
        "build",
        "*.min.js",
        "*.lock",
        ".venv",
        "venv",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    ]

    # --- API -------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- Logging ---------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = False


# Singleton — import this everywhere
settings = Settings()
