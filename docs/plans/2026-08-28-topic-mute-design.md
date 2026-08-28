# Topic Inbound Mute Design

## Goal

Allow a user to stop and resume inbound `MAX -> Telegram` synchronization for an
individual Telegram topic without deleting the topic, its history, or its MAX
mapping. Reconcile should also mute a channel when MAX confirms that the current
account is no longer a participant.

## Behavior

- `/mute` must be sent inside a mapped Telegram topic.
- `/unmute` must be sent inside a mapped Telegram topic.
- Muting disables only inbound delivery. Telegram messages sent to the topic
  continue to use the existing outbound `Telegram -> MAX` path.
- Mute state is stored in SQLite and survives restarts, `/start`, and `/resync`.
- A manually muted topic is never automatically unmuted.
- Reconcile automatically mutes a MAX channel when a fresh per-chat lookup shows
  that the current MAX account ID is absent from `participants`.
- Telegram topics and mappings are preserved. No message, cursor, or topic is
  deleted.

## Architecture

`TelegramTopic` owns an `inbound_enabled` flag persisted in `telegram_topics`.
The repository exposes a scoped update method requiring both
`telegram_user_id` and `telegram_topic_id`. A small application service provides
the command use cases so Telegram handlers do not implement persistence rules.

`InboundSyncService` checks the flag before live delivery, dirty-chat polling,
reconnect recovery, and hourly catch-up. Muted topics are skipped before calling
`fetch_history()`.

When `/unmute` enables delivery, the repository stores `inbound_since_ms`.
History messages older than that boundary are skipped while advancing the sync
cursor, so the muted backlog is not replayed and only new messages are delivered.

The MAX port exposes a targeted chat-state lookup. `PymaxAdapter` derives the
current account ID from `WebClient.me.contact.id` and reports channel membership
from `participants`. Reconcile checks existing mappings that are absent from the
current chat list and automatically disables inbound delivery only when the
targeted lookup explicitly confirms a channel with missing membership. Missing
or failed lookups do not change state.

## Error Handling

Commands outside a topic receive an explanatory response. Commands in an
unknown topic report that no MAX mapping exists. Repository updates remain
user-scoped. MAX lookup failures are logged and leave the existing mute state
unchanged.

## Verification

- Repository migration and persistence tests.
- Handler tests for `/mute`, `/unmute`, outside-topic usage, and unknown topics.
- Inbound tests proving muted topics skip live delivery and history requests.
- Reconcile tests proving explicit channel non-membership auto-mutes while
  failures and subscribed channels do not.
- Full formatting, linting, type checking, architecture tests, and pytest suite.
