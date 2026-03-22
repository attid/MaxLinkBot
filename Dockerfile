FROM python:3.13-slim AS builder

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Production image — only runtime deps needed
FROM python:3.13-slim

WORKDIR /app

# Install uv and production dependencies in one layer
COPY pyproject.toml uv.lock ./
RUN pip install uv && \
    uv sync --frozen --no-dev

# Copy application code
COPY src/ ./src/

# Non-root user for security
RUN useradd --create-home --shell /bin/bash appuser && \
    mkdir -p /data && chown appuser:appuser /data
USER appuser

ENV PYTHONPATH="/app"
ENV PATH="/app/.venv/bin:$PATH"

# Volume for SQLite persistence
VOLUME ["/data"]

ENTRYPOINT ["python", "-m", "src.main"]
