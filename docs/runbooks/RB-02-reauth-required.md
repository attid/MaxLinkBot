# RB-02: Reauth Required — MAX Session Expired

## Symptoms
- User receives Telegram message: "Your MAX session has expired."
- Bot logs show `BINDING_REAUTH_REQUIRED` audit events.
- User's messages from topics stop syncing to MAX.
- MAX → Telegram delivery continues until background health check detects expiry.

## Diagnosis

1. Check audit events:
   ```bash
   docker compose exec maxlinkbot python -c "
   import asyncio, aiosqlite
   async def check():
       db = await aiosqlite.connect('/data/maxlinkbot.db')
       async with db.execute(
           \"SELECT telegram_user_id, event_type, detail, created_at \"
           \"FROM audit_events ORDER BY created_at DESC LIMIT 20\"
       ) as cur:
           rows = await cur.fetchall()
       for r in rows:
           print(r)
       await db.close()
   asyncio.run(check())
   "
   ```

2. Check binding status:
   ```sql
   SELECT telegram_user_id, status, updated_at FROM user_bindings;
   ```

## Resolution

1. Notify user to send `/start` to the bot.
2. User completes MAX auth flow.
3. Bot automatically runs reconcile, recreates topics if needed.
4. Verify with:
   ```bash
   docker compose logs maxlinkbot --since 5m | grep -i reconcile
   ```

## Prevention
- Sessions expire based on MAX token TTL.
- Background HealthCheckService checks validity every poll interval.
- Notification cooldown is 24 hours — user will only be notified once per day per expiry event.
