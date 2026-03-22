# Configuration Reference

All settings are environment variables. No config files.

## Source of Truth

Environment variables are the only configuration mechanism.

## Variables

### Required

| Variable | Type | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `str` | Telegram bot token from @BotFather |
| `ALLOWED_TELEGRAM_USER_IDS` | `str` | Comma-separated Telegram user IDs |
| `MAX_BASE_URL` | `str` | Pumax MAX API base URL |
| `DATABASE_URL` | `str` | SQLite connection string, e.g. `sqlite+aiosqlite:///data/maxlinkbot.db` |

### Optional

| Variable | Default | Description |
|---|---|---|
| `POLL_INTERVAL_SECONDS` | `30` | Background poll interval per active binding |
| `BACKFILL_MESSAGE_COUNT` | `5` | Number of historical messages to pull on topic creation |
| `LOG_LEVEL` | `INFO` | Logging level |

## ALLOWED_TELEGRAM_USER_IDS Format

Comma-separated list of integer Telegram user IDs:

```
ALLOWED_TELEGRAM_USER_IDS="123456789,987654321"
```

No spaces. No other formats in v1.

## DATABASE_URL Format

SQLite via aiosqlite:

```
DATABASE_URL="sqlite+aiosqlite:///data/maxlinkbot.db"
```

The path before `///` is the directory. The path after is the database filename.

## Decision: Env over Config File

**Why:** Env is the standard for 12-factor apps and container deployments. No extra files to mount or template.
**Why not config file:** Adds complexity with no benefit for a single-host bot.

## Decision: No Secrets in Env Defaults

All secrets (`TELEGRAM_BOT_TOKEN`) must be provided at runtime. No defaults.
