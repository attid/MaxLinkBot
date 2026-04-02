FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

COPY src/ ./src/
COPY scripts/ ./scripts/

RUN useradd --create-home --shell /bin/bash appuser && \
    mkdir -p /data && chown appuser:appuser /data && \
    chmod +x /app/scripts/healthcheck.sh
USER appuser

ENV PYTHONPATH="/app"

VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD ["/app/scripts/healthcheck.sh"]

ENTRYPOINT ["/app/.venv/bin/python", "-m", "src.main"]
