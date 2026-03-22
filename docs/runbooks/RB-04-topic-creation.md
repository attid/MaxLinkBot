# RB-04: Telegram Topic Creation Failures

## Symptoms
- `TOPIC_CREATED` audit events not appearing after `/start`.
- User's MAX chats are not creating Telegram topics.
- Bot logs show errors related to topic creation.

## Diagnosis

1. Check recent audit events:
   ```sql
   SELECT telegram_user_id, event_type, detail, created_at
   FROM audit_events
   WHERE event_type = 'topic_created' OR event_type = 'unknown_error'
   ORDER BY created_at DESC LIMIT 20;
   ```

2. Check if MAX chats were fetched:
   ```sql
   SELECT max_chat_id, binding_telegram_user_id, title
   FROM max_chats WHERE binding_telegram_user_id = <user_id>;
   ```

3. Check existing topic mappings:
   ```sql
   SELECT * FROM telegram_topics WHERE telegram_user_id = <user_id>;
   ```

## Common Causes

### Bot is not admin/creator of user's private chat
- Telegram topics can only be created in group chats or by bots with admin rights.
- Note: Bot-to-user private chats do NOT support topics in standard Telegram.
- **Fix**: Bot must be added to a group chat, and the user must be in that group.

### Reconciliation not triggered
- User hasn't sent `/start`.
- Fix: Ask user to send `/start`.

### MAX API error
- `list_personal_chats` fails with network or auth error.
- Fix: Check MAX connectivity and session validity.

## Resolution
1. Verify bot is in a group chat (not direct bot-to-user private chat).
2. Verify bot has admin/creator rights in the group.
3. User sends `/start` to trigger reconcile.
4. Topics are created with the chat title as the topic name.
