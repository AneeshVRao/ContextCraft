# ContextCraft — Multi-stage Docker build
# Stage 1: Build
FROM python:3.12-slim AS builder

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir build && \
    python -m build --wheel --outdir /app/dist

# Stage 2: Runtime
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install git for git blame / history features
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/dist/*.whl /tmp/

RUN pip install --no-cache-dir /tmp/*.whl && \
    rm -f /tmp/*.whl

# Default: run the API server
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "contextcraft.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
