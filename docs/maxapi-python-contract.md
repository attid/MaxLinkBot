# maxapi-python Contract — Known Limitations And Verified Facts

> **Status:** This document captures the current repository knowledge about the MAX client integration. Update it whenever the integration contract changes or new constraints are discovered.

## Library

`maxapi-python` — Python package for MAX WebSocket client integration.

Pinned version: `2.4.1` (upgraded from `2.3.1`, see ADR-0005)

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
- PyMax stores token, device ID and sync markers in table `sessions`. The 2.4
  session store extends an existing database schema with missing columns
  (`_ensure_column`) and adds a nullable `user_agent` column on first open; an
  existing 2.3 session database keeps its token, `device_id` and
  `mt_instance_id` and is upgraded in place.
- Device identity for MAX comes from `session.device_id`, not from the user
  agent: on restore PyMax reuses the stored `device_id` and only fills in a
  generated user agent when the session has none.
- In PyMax 2.4 `client.me` and `client.chats` are read-only properties backed by
  the runtime app: accessing them before `start()` raises
  `RuntimeError("Client runtime is not initialized")`. The adapter accesses them
  only for started clients and additionally tolerates that error.
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
- Channel publications may expose `sender=0` because they have no separate user
  sender. Inbound delivery uses the persisted MAX chat title as the source label
  and omits the meaningless sender ID from the Telegram prefix.
- A departed public channel may remain available through targeted `get_chat()`
  with `status='ACTIVE'`, so chat status is not a reliable subscription signal.
  In verified PyMax 2.3.1 responses, the current MAX account ID is present in
  `Chat.participants` for a subscribed channel and absent after departure.
- `fetch_chats()` may omit a departed channel while its public history remains
  readable by chat ID. Reconcile therefore uses a targeted chat lookup for stale
  topic mappings and disables inbound synchronization only when channel
  non-membership is explicitly confirmed.
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
- MAX may return video playback URLs as dynamic `MP4_<quality>` keys without a
  `cache` field. PyMax 2.4.1 fixed this upstream: `VideoRequest.cache` has a
  default and a validator picks the highest available `MP4_<quality>` URL, so the
  adapter no longer needs the MLB-027 compatibility fallback that recovered the
  URL from a Pydantic `ValidationError`. Signed URLs are never written to logs.
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
- PyMax decodes LZ4 payload coefficients and Zstandard payloads.
- PyMax 2.4.1 adds `PollAttachment`, `Voice`/`VideoNote` sending and keeps unknown
  attachments as `UnknownAttachment`, so unsupported MAX content still cannot
  break message parsing. The adapter does not render polls, voice messages or
  video notes yet; they fall back to the generic text representation.
- Forwarded / linked MAX messages may expose the actual supported payload under
  `message.link.message` while the top-level message stays effectively empty
  (`type=USER`, no text/attaches usable for rendering). Adapter code preserves
  top-level sender/time/id metadata, but reads content/media metadata from either
  object-shaped or dict-shaped `link.message`.
- A MAX album is one message with several `attaches` entries, not several
  messages. `PymaxAdapter` therefore exposes every renderable attachment through
  the `media: list[{type, url, file_name}]` payload key for both `get_messages()`
  and `drain_buffered_messages()`; the legacy `media_url` / `file_name` / `type`
  keys stay as a view of the first element.
- `MAX -> Telegram` delivery of a message with two or more photo/video elements
  uses the Bot API media group path (`sendMediaGroup`, max 10 items per group).
  Documents are only grouped with documents; mixed photo+document or audio
  payloads keep the single-media path. Media group items are uploaded per item
  (video/document as `BufferedInputFile`) because Telegram cannot fetch MAX
  signed URLs for those types; photo items may stay URL-based.
- Telegram media group captions follow the same rule as single media: first 1024
  characters on the first element, the remainder as follow-up text messages.

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
