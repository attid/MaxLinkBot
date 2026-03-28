# Configuration Reference

All settings are environment variables. No config files.

## Source of Truth

Environment variables are the only configuration mechanism.

## Variables

### Required

| Variable | Type | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `str` | Telegram bot token from @BotFather |

### Optional

| Variable | Default | Description |
|---|---|---|
| `ALLOWED_TELEGRAM_USER_IDS` | `""` | Comma-separated Telegram user IDs (empty = no one allowed) |
| `MAX_WORK_DIR` | `/data/max_sessions` | Directory for per-user MAX session data |
| `DATABASE_URL` | `sqlite+aiosqlite:////data/maxlinkbot.db` | SQLite connection string |
| `POLL_INTERVAL_SECONDS` | `30` | Background poll interval per active binding |
| `HEALTH_CHECK_INTERVAL_SECONDS` | `300` | Interval between MAX session health checks |
| `CATCHUP_INTERVAL_SECONDS` | `3600` | Full inbound catch-up interval for existing topics |
| `RECONNECT_STORM_THRESHOLD` | `5` | Reconnect count within the storm window that marks runtime unhealthy |
| `RECONNECT_STORM_WINDOW_SECONDS` | `300` | Time window for reconnect storm detection |
| `RUNTIME_UNHEALTHY_MARKER_PATH` | `/tmp/maxlinkbot.unhealthy` | Marker file used by container healthcheck |
| `BACKFILL_MESSAGE_COUNT` | `5` | Number of historical messages to pull on topic creation |
| `LOG_LEVEL` | `INFO` | Logging level |

## ALLOWED_TELEGRAM_USER_IDS Format

Comma-separated list of integer Telegram user IDs:

```
ALLOWED_TELEGRAM_USER_IDS="123456789,987654321"
```

No spaces.

## DATABASE_URL Format

SQLite via aiosqlite. Path is relative inside the container unless it starts with `/`:

```
# Relative (inside volume mounted at /data)
DATABASE_URL="sqlite+aiosqlite:///data/maxlinkbot.db"

# Absolute (4 slashes)
DATABASE_URL="sqlite+aiosqlite:////var/lib/maxlinkbot.db"

# In-memory (testing)
DATABASE_URL="sqlite+aiosqlite://:memory:"
```

## Decision: Env over Config File

**Why:** Env is the standard for 12-factor apps and container deployments. No extra files to mount or template.
**Why not config file:** Adds complexity with no benefit for a single-host bot.

## Runtime Healthcheck

Container health is not process-liveness only. The bot writes an unhealthy marker file when inbound runtime degrades, for example on a reconnect storm. Docker healthcheck treats the container as unhealthy when `RUNTIME_UNHEALTHY_MARKER_PATH` exists.

## Decision: No Secrets in Env Defaults

All secrets (`TELEGRAM_BOT_TOKEN`) must be provided at runtime. No defaults.
