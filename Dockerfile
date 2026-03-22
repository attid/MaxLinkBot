FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

COPY src/ ./src/

RUN useradd --create-home --shell /bin/bash appuser && \
    mkdir -p /data && chown appuser:appuser /data
USER appuser

ENV PYTHONPATH="/app"

VOLUME ["/data"]

ENTRYPOINT ["/app/.venv/bin/python", "-m", "src.main"]
