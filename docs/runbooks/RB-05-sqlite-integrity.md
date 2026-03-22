# RB-05: SQLite Integrity Check

## Symptoms
- `sqlite3OperationalError` or `sqlite3DatabaseError` in logs.
- Bot crashes on startup.
- Data loss or duplicate messages after unexpected restart.

## Diagnosis

1. Check SQLite file exists and is accessible:
   ```bash
   docker compose exec maxlinkbot ls -la /data/maxlinkbot.db
   ```

2. Run integrity check:
   ```bash
   docker compose exec maxlinkbot python -c "
   import asyncio, aiosqlite
   async def integrity():
       db = await aiosqlite.connect('/data/maxlinkbot.db')
       result = await db.execute('PRAGMA integrity_check').fetchone()
       print('Integrity:', result[0])
       await db.close()
   asyncio.run(integrity())
   "
   ```

3. Check for corruption (expected: "ok"):
   ```
   Integrity: ok
   ```

## Tables and Their Role

| Table | Purpose |
|---|---|
| `user_bindings` | Telegram → MAX session mapping |
| `max_chats` | Known MAX chats per user |
| `telegram_topics` | Topic ID ↔ MAX chat ID mapping |
| `message_links` | Delivery idempotency (dedup) |
| `sync_cursors` | Last-seen message per chat |
| `audit_events` | Audit log |

## Common Issues

### Empty database after restart
- Volume not mounted correctly.
- Fix: Verify `maxlinkbot-data` volume is created and persistent.

### Database locked
- Multiple processes accessing SQLite simultaneously.
- Fix: Only one bot instance should run at a time.

### Corruption after hard crash
- Unclean shutdown corrupts WAL/journal.
- Fix: Run `PRAGMA integrity_check`. If corruption detected:
  ```bash
  # Export data
  docker compose exec maxlinkbot python -c "
  import asyncio, aiosqlite, json
  async def export():
      db = await aiosqlite.connect('/data/maxlinkbot.db')
      for table in ['user_bindings','max_chats','telegram_topics','message_links','sync_cursors']:
          async with db.execute(f'SELECT * FROM {table}') as cur:
              rows = await cur.fetchall()
          print(f'{table}: {len(rows)} rows')
      await db.close()
  asyncio.run(export())
  "
  ```
  Then restore from backup or re-run reconcile.

## Prevention
- Always use `docker compose down` (not `docker kill`).
- Schedule regular volume backups.
- Run `PRAGMA integrity_check` weekly.
