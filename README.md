# MaxLinkBot

Personal multi-user Telegram-to-MAX gateway via `maxapi-python`.

One bot serves several allowed Telegram users — each with their own MAX account, isolated from each other.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run linting, type-checking and tests
just check

# Run tests only
just test

# Format code
just fmt

# Lint only
just lint
```

## Configuration

All configuration is via environment variables.

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token from @BotFather |
| `ALLOWED_TELEGRAM_USER_IDS` | Yes | Comma-separated list of allowed Telegram user IDs |
| `MAX_WORK_DIR` | No | Directory for per-user MAX session data |
| `DATABASE_URL` | Yes | SQLite path, e.g. `sqlite+aiosqlite:///data/maxlinkbot.db` |
| `POLL_INTERVAL_SECONDS` | No | Background poll interval (default: 30) |
| `BACKFILL_MESSAGE_COUNT` | No | Number of messages to backfill on topic creation (default: 5) |
| `LOG_LEVEL` | No | Log level (default: INFO) |

## Docker Deployment

```bash
# Build and start
docker compose up -d --build

# View logs
docker compose logs -f maxlinkbot

# Stop
docker compose down
```

Create a `.env` file:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
ALLOWED_TELEGRAM_USER_IDS=123456789,987654321
MAX_WORK_DIR=/data/max_sessions
DATABASE_URL=sqlite+aiosqlite:////data/maxlinkbot.db
POLL_INTERVAL_SECONDS=30
BACKFILL_MESSAGE_COUNT=5
LOG_LEVEL=INFO
```

SQLite data is persisted in the `maxlinkbot-data` Docker volume.

## Architecture

See `docs/architecture.md` for full layer diagram and `docs/conventions.md` for code style.

## Key Services

- `AllowlistGate` — discards all updates from non-allowed users
- `AuthorizationFlowService` — conducts user through MAX auth flow
- `RefreshReconcileService` — used by `/start`; checks session, chats, topics, backfills
- `InboundSyncService` — delivers MAX → Telegram
- `OutboundSyncService` — delivers Telegram topic → MAX
- `HealthCheckService` — marks binding as `reauth_required`, notifies user, stops poll
- `BackgroundPoller` — background loop that polls all active bindings

## Runbooks

See [`docs/runbooks/`](docs/runbooks/) for operational guides:
- [RB-01](docs/runbooks/RB-01-initial-setup.md) — Initial Docker setup
- [RB-02](docs/runbooks/RB-02-reauth-required.md) — Session expired / reauth required
- [RB-03](docs/runbooks/RB-03-no-new-messages.md) — No new messages from MAX
- [RB-04](docs/runbooks/RB-04-topic-creation.md) — Telegram topic creation failures
- [RB-05](docs/runbooks/RB-05-sqlite-integrity.md) — SQLite integrity check

---

## Acceptance Checklist — v1.0

All items must pass before considering the system production-ready.

### Functional Requirements

- [ ] **AUTH-01**: Allowlisted user can complete MAX auth via `/start`
- [ ] **AUTH-02**: Non-allowlisted users are silently ignored
- [ ] **AUTH-03**: Expired session transitions binding to `reauth_required`
- [ ] **AUTH-04**: Re-auth flow updates existing binding (no duplicate)

- [ ] **RECONCILE-01**: `/start` fetches all MAX personal chats
- [ ] **RECONCILE-02**: New chats create Telegram topics with backfill (last 5 messages)
- [ ] **RECONCILE-03**: Existing chats do not duplicate topics
- [ ] **RECONCILE-04**: Chat titles are preserved as topic names

- [ ] **INBOUND-01**: New MAX messages are delivered to correct Telegram topic
- [ ] **INBOUND-02**: Already-delivered messages are not re-sent (idempotency)
- [ ] **INBOUND-03**: Unsupported media types show `[type]: description` fallback
- [ ] **INBOUND-04**: Cursor advances after each successful poll

- [ ] **OUTBOUND-01**: Message from Telegram topic is sent to correct MAX chat
- [ ] **OUTBOUND-02**: Message outside topic receives service reply
- [ ] **OUTBOUND-03**: Delivery failures are logged to audit

- [ ] **BACKGROUND-01**: BackgroundPoller polls all ACTIVE bindings
- [ ] **BACKGROUND-02**: HealthCheckService marks expired sessions as `reauth_required`
- [ ] **BACKGROUND-03**: Reauth notification sent at most once per 24 hours per user
- [ ] **BACKGROUND-04**: `REAUTH_REQUIRED` bindings are skipped by poller

### Non-Functional Requirements

- [ ] **OPS-01**: Application starts in Docker with documented env vars
- [ ] **OPS-02**: SQLite data persists across container restarts (volume)
- [ ] **OPS-03**: All tests pass (`just test`)
- [ ] **OPS-04**: Pyright strict mode reports 0 errors (`just typecheck`)
- [ ] **OPS-05**: Ruff reports 0 violations (`just lint`)
- [ ] **OPS-06**: Architecture boundary test passes (`just arch-test`)

### Security Requirements

- [ ] **SEC-01**: No credentials stored in code (all via env)
- [ ] **SEC-02**: User cannot access another user's topic mappings (user isolation)
- [ ] **SEC-03**: Non-allowlisted users produce no bot response (silent rejection)
