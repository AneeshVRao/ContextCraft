"""Shared HTTP client timeout defaults for external API calls."""

from __future__ import annotations

import httpx

# Ollama: fail fast on connect; cap read so a slow local server cannot hang forever.
OLLAMA_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)

# OpenAI / Anthropic / Cohere / generic outbound HTTP.
DEFAULT_HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)
