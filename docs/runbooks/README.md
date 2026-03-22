# Runbooks

Operational guides for MaxLinkBot v1.

## Index

| ID | Title | When to Use |
|---|---|---|
| [RB-01](RB-01-initial-setup.md) | Initial Docker Setup | First deploy, missing env vars |
| [RB-02](RB-02-reauth-required.md) | Reauth Required | User sees "session expired" message |
| [RB-03](RB-03-no-new-messages.md) | No New Messages from MAX | MAX messages not appearing in Telegram |
| [RB-04](RB-04-topic-creation.md) | Topic Creation Failures | Topics not created after `/start` |
| [RB-05](RB-05-sqlite-integrity.md) | SQLite Integrity Check | Database errors, corruption suspected |

## Quick Diagnostics

```bash
# View recent logs
docker compose logs -f maxlinkbot

# Check active bindings
docker compose exec maxlinkbot python -c "
import asyncio, aiosqlite
async def status():
    db = await aiosqlite.connect('/data/maxlinkbot.db')
    async with db.execute('SELECT telegram_user_id, status, updated_at FROM user_bindings') as c:
        for r in await c.fetchall(): print(r)
    await db.close()
asyncio.run(status())
"

# Check recent audit events
docker compose exec maxlinkbot python -c "
import asyncio, aiosqlite
async def audit():
    db = await aiosqlite.connect('/data/maxlinkbot.db')
    async with db.execute('SELECT telegram_user_id, event_type, detail, created_at FROM audit_events ORDER BY id DESC LIMIT 20') as c:
        for r in await c.fetchall(): print(r)
    await db.close()
asyncio.run(audit())
"
```
