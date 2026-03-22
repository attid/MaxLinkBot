# RB-02: Reauth Required — MAX Session Expired

## Symptoms
- User receives Telegram message: "Your MAX session has expired."
- Bot logs show `BINDING_REAUTH_REQUIRED` audit events.
- User's messages from topics stop syncing to MAX.
- MAX → Telegram delivery continues until background health check detects expiry.
- After manual deletion of `MAX_WORK_DIR/{telegram_user_id}/session.db`, the next background health check should move the binding to `reauth_required` instead of printing a QR flow in container logs.

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

3. Check persisted session file:
   ```bash
   ls -l /data/max_sessions/<telegram_user_id>/session.db
   ```
   If the file is missing while `user_bindings.status='active'`, the next health check should force `reauth_required`.

4. Check whether the persisted session is actually authorized:
   ```bash
   sqlite3 /data/max_sessions/<telegram_user_id>/session.db "SELECT token, device_id FROM auth;"
   ```
   A row with empty `token` means the QR/login flow was started but not completed; background runtime should still force `reauth_required`.

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
