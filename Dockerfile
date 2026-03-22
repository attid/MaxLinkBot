FROM python:3.13-slim AS builder

WORKDIR /app

# Install uv for fast package management
RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Production image
FROM python:3.13-slim

WORKDIR /app

# Install uv and production dependencies in one layer
RUN pip install uv && \
    uv sync --frozen --no-dev

COPY --from=builder /app/src ./src
COPY --from=builder /app/.venv/lib /app/.venv/lib

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

# Non-root user for security
RUN useradd --create-home --shell /bin/bash appuser && \
    mkdir -p /data && chown appuser:appuser /data
USER appuser

# Volume for SQLite persistence
VOLUME ["/data"]

ENTRYPOINT ["python", "-m", "src.main"]
