# maxapi-python Contract — Known Limitations And Verified Facts

> **Status:** This document captures the current repository knowledge about the MAX client integration. Update it whenever the integration contract changes or new constraints are discovered.

## Library

`maxapi-python` — Python package for MAX WebSocket client integration.

Pinned version: `2.3.1`

Python runtime API: `from pymax import ExtraConfig, File, Photo, WebClient`

## Verified In Repository

- Authentication is WebSocket-based.
- The current integration uses `WebClient` and QR/session-based auth.
- QR URLs are captured through a public `QrHandler` implementation and rendered to PNG
  for Telegram; private PyMax methods are not patched.
- An active binding is saved only after PyMax emits `on_start()`, which means QR
  confirmation completed and the token was persisted. QR expiry/startup errors are
  translated to `AuthError` and the client is closed.
- Session data is persisted on disk in per-user directories under `MAX_WORK_DIR/{telegram_user_id}/`.
- The persisted restore artifact currently expected by the repository is `MAX_WORK_DIR/{telegram_user_id}/session.db`.
- PyMax 2.3 stores token, device ID and sync markers in table `sessions`.
- On first use, a PyMax 1.2.5 row from legacy table `auth` is copied into `sessions`.
  The `auth` table is preserved for rollback.
- A merely existing `session.db` is not enough for restore: background runtime requires
  a non-empty token in `sessions`.
- The runtime keeps one logical MAX session per Telegram user binding.
- The project wraps the external client behind its own adapter in `src/infrastructure/max/adapter.py`.
- `WebClient.fetch_chats()` may return `ChatType.DIALOG` chats with `title=None`; for those chats the usable identity comes from `participants` and `owner`.
- The MAX adapter validates the chat fields used by the application and exposes them
  through `PersonalChatData`: string `max_chat_id`, string `title`, and optional
  `participant_ids: list[str]`. Reconcile does not consume untyped PyMax chat objects.
- `WebClient.fetch_users()` / `get_cached_user()` return `User` objects whose display names are available via `user.names[]`.
- `WebClient.fetch_history()` exposes sender identity as an ID and message time as an epoch-milliseconds timestamp.
- `WebClient.send_message()` accepts outgoing media through `attachments=[Photo(...)]`
  and `attachments=[File(...)]`.
- For inbound polling, adapter code must not assume that `WebClient.fetch_history()` is ordered `newest -> oldest`; filtering by cursor has to scan the whole returned batch instead of stopping at the first old message.
- `WebClient` supports live inbound handling through `on_message()`; the adapter buffers
  handler events and the application drains them as the primary `MAX -> Telegram` transport.
- PyMax 2.3.1 `Message` exposes the sender identifier as `sender: int | None`,
  without a separate `sender_id` field. History and live paths both normalize
  this field into the adapter's `sender_id` and resolve `sender_name` through the
  MAX user cache/API.
- `on_start()` runs again after a successful reconnect and is used as the adapter's
  reconnect signal.
- While `WebClient.start()` is running, shutdown has a single owner: the adapter
  cancels and awaits that task, and PyMax closes its connection and session store
  from the task's `CancelledError` path. Calling `WebClient.close()` concurrently
  can race on the same `aiosqlite` store and hang process shutdown.
- `fetch_history()` remains a fallback catch-up path and should not be used as a high-frequency steady-state polling mechanism for every chat.
- Human-readable titles for MAX dialogs can be resolved as "the participant whose ID differs from chat.owner".
- Background/runtime `start()` paths are restore-only: if `session.db` is missing or
  `sessions.token` is empty, the adapter raises `AuthError` instead of starting QR auth.
- A PyMax `ApiError` from the LOGIN opcode is translated to application `AuthError`, so
  the existing reauth flow handles a rejected migrated token instead of hanging startup.
- Incoming `FileAttachment` contains `file_id`, name, size and token but no direct URL.
  The adapter resolves a temporary download URL through `WebClient.get_file_by_id()`.
- Incoming `VideoAttachment` contains `video_id` but no direct URL. The adapter resolves
  it through `WebClient.get_video_by_id()` using the top-level message ID.
- In PyMax 2.3 history, forwarded `link.message` may remain a plain camelCase dict
  instead of a typed model. The adapter supports both dict-shaped and object-shaped
  linked content and preserves the top-level message ID for video URL resolution.
- MAX video delivery to Telegram uses the Bot API `sendVideo` path. Videos up to the
  documented 50 MB limit are downloaded with MAX-compatible headers and uploaded as
  MPEG4; larger videos use an explicit `[video]: URL` fallback without full download.
- Telegram media captions are limited to 1024 characters. The adapter preserves
  longer MAX text by sending the first 1024 characters with photo/audio/video/document
  and the complete remainder as one or more topic messages of at most 4096 characters.
  Telegram API errors are not rewritten as media download failures.
- Unknown attachment types are represented by PyMax `UnknownAttachment` instead of
  failing the complete message parse.
- PyMax 2.3.1 decodes LZ4 payload coefficients and Zstandard payloads.
- Forwarded / linked MAX messages may expose the actual supported payload under
  `message.link.message` while the top-level message stays effectively empty
  (`type=USER`, no text/attaches usable for rendering). Adapter code preserves
  top-level sender/time/id metadata, but reads content/media metadata from either
  object-shaped or dict-shaped `link.message`.

## Known Unknowns

The following still need explicit confirmation or stronger documentation:

1. **Session lifecycle details:**
   - What exact events or exceptions indicate expired auth versus transient disconnect?
   - Will every production token created by 1.2.5 remain accepted after schema migration?

2. **Chat and message model details:**
   - Which fields on chats/messages are stable enough to rely on as long-term identifiers?
   - Which media/message types are supported end-to-end in v1 without fallback text?

3. **Polling and reconnect behavior:**
   - What reconnect/backoff behavior should be considered acceptable for background delivery?
   - Which adapter states should be treated as recoverable versus `reauth_required`?
   - Does the production WebSocket remain stable through a multi-hour soak test?

4. **Operational contract:**
   - What diagnostics should be documented for broken or partial session directories?

## Action Items

- [ ] Document exact auth/session failure modes observed in production-like runs
- [ ] Expand the list of supported message/media types with confirmed behavior
- [ ] Add references to concrete adapter methods and invariants as they stabilize

## How To Update This Document

When a new fact about the MAX client integration is discovered:
1. Move the item from "Known Unknowns" to "Verified In Repository"
2. Record the exact method, exception, or runtime behavior
3. Add any new unknown that appears during implementation or operations
