"""Application settings loaded from environment variables.

Uses pydantic-settings so every value can be overridden via env vars
prefixed with ``CONTEXTCRAFT_``.  A ``.env`` file in the project root
is loaded automatically.

Railway and other hosts often set ``DATABASE_URL`` without the prefix;
that alias is accepted for ``database_url``.
"""

from __future__ import annotations

from typing import Self

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from contextcraft.security import validate_ollama_base_url


class Settings(BaseSettings):
    """Central configuration for ContextCraft."""

    model_config = SettingsConfigDict(
        env_prefix="CONTEXTCRAFT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_version: str = "0.3.0"

    # --- Database --------------------------------------------------------
    database_url: str = Field(
        default="postgresql://contextcraft:contextcraft@localhost:5432/contextcraft",
        validation_alias=AliasChoices("CONTEXTCRAFT_DATABASE_URL", "DATABASE_URL"),
    )

    db_min_connections: int = 2
    db_max_connections: int = 20  # sized for concurrent indexing + API serving

    # --- Embeddings ------------------------------------------------------
    embedding_provider: str = "gemini"  # "openai" | "gemini"
    openai_api_key: str = ""
    gemini_api_key: str = ""
    embedding_model: str = "text-embedding-004"  # Gemini default
    embedding_dimensions: int = 768  # Gemini text-embedding-004 dim
    embedding_batch_size: int = 100
    embedding_max_concurrent: int = 5

    # --- LLM -------------------------------------------------------------
    llm_provider: str = "gemini"  # "openai" | "anthropic" | "ollama" | "gemini"
    openai_chat_model: str = "gpt-4o"
    gemini_chat_model: str = "gemini-1.5-flash"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    # Allow non-localhost Ollama hosts (SSRF risk — trusted deployments only).
    ollama_allow_remote: bool = False

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
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    # --- Logging ---------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = False

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def validate_ollama_url(self) -> Self:
        self.ollama_base_url = validate_ollama_base_url(
            self.ollama_base_url,
            allow_remote=self.ollama_allow_remote,
        )
        return self


# Singleton — import this everywhere
settings = Settings()
