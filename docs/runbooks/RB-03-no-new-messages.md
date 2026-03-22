# RB-03: No New Messages from MAX

## Symptoms
- Messages sent in MAX do not appear in Telegram topics.
- User confirms messages exist in MAX but Telegram is silent.

## Diagnosis

1. Check sync cursors — are they advancing?
   ```sql
   SELECT max_chat_id, binding_telegram_user_id, last_max_message_id, updated_at
   FROM sync_cursors;
   ```

2. Check if topics exist for the user's chats:
   ```sql
   SELECT tt.telegram_topic_id, tt.telegram_user_id, tt.max_chat_id, mc.title
   FROM telegram_topics tt
   JOIN max_chats mc ON mc.max_chat_id = tt.max_chat_id
   WHERE tt.telegram_user_id = <user_id>;
   ```

3. Check for DELIVERY_FAILED audit events:
   ```sql
   SELECT telegram_user_id, detail, created_at
   FROM audit_events
   WHERE event_type = 'delivery_failed'
   ORDER BY created_at DESC LIMIT 10;
   ```

4. Verify bot is polling — check process is alive:
   ```bash
   docker compose ps
   docker compose logs maxlinkbot --since 5m | grep -i poll
   ```

## Common Causes

### No topic mapping
- MAX chat has no corresponding Telegram topic.
- Fix: Ask user to run `/start` to trigger reconcile.

### Cursor stuck
- SyncCursor is not advancing because MAX has no new messages since last cursor.
- This is expected behavior if MAX truly has no new messages.
- Verify by checking MAX directly for unread messages.

### DELIVERY_FAILED audit events
- Telegram API errors (rate limiting, bot blocked by user).
- Fix: Check Telegram API status. User may have blocked the bot.

### MAX session issues
- MAX client errors in logs (WebSocket disconnection, auth errors).
- Fix: Check `MAX_WORK_DIR` is writable and session files exist for the user.

## Resolution
1. Run reconcile for affected user: ask them to send `/start`.
2. If Telegram API issue: resolve upstream.
3. If MAX session issue: check `MAX_WORK_DIR/{telegram_user_id}/session.db` exists.
