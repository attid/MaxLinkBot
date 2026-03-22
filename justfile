set dotenv-load := true

# Default: full check
default: check

# Auto-format code (ruff)
fmt:
  uv run ruff check --fix .
  uv run ruff format .

# Run linters (ruff)
lint:
  uv run ruff check .

# Run type checker (pyright)
typecheck:
  uv run pyright

# Fast unit tests
test-fast:
  uv run pytest tests/ -m "not slow" -q

# Full test suite
test:
  uv run pytest tests/ -q

# Full check: fmt + lint + typecheck + test
check: fmt lint typecheck test

# Structural architecture tests
arch-test:
  uv run python .linters/check_imports.py

# Show local metrics
metrics:
  uv run python .linters/metrics.py

# Remove build artifacts
clean:
  rm -rf .pytest_cache .ruff_cache dist build *.egg-info
  find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
  find . -type f -name "*.pyc" -delete

# Run bot in docker — uses ./data for session + DB
run:
  docker build -t maxlinkbot:test .
  docker run --rm --name maxlinkbot \
    -v $(pwd)/data:/data \
    -e TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN} \
    -e ALLOWED_TELEGRAM_USER_IDS=${ALLOWED_TELEGRAM_USER_IDS} \
    maxlinkbot:test
