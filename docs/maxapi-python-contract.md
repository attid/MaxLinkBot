# maxapi-python Contract — Known Limitations And Verified Facts

> **Status:** This document captures the current repository knowledge about the MAX client integration. Update it whenever the integration contract changes or new constraints are discovered.

## Library

`maxapi-python` — Python package for MAX WebSocket client integration.

Installation: `pip install maxapi-python`

Python import path: `from pymax import MaxClient`

## Verified In Repository

- Authentication is WebSocket-based.
- The current integration uses QR/session-based auth with `device_type="WEB"`.
- Session data is persisted on disk in per-user directories under `MAX_WORK_DIR/{telegram_user_id}/`.
- The persisted restore artifact currently expected by the repository is `MAX_WORK_DIR/{telegram_user_id}/session.db`.
- A merely existing `session.db` is not enough for restore: the repository currently treats the session as reusable only when table `auth` contains at least one non-empty `token`.
- The runtime keeps one logical MAX session per Telegram user binding.
- The project wraps the external client behind its own adapter in `src/infrastructure/max/adapter.py`.
- `MaxClient.fetch_chats()` may return `ChatType.DIALOG` chats with `title=None`; for those chats the usable identity comes from `participants` and `owner`.
- `MaxClient.fetch_users()` / `get_cached_user()` return `User` objects whose display names are available via `user.names[]`.
- `MaxClient.fetch_history()` exposes sender identity as an ID (`sender` / `sender_id`) and message time as an epoch-milliseconds timestamp.
- `MaxClient.send_message()` supports generic attachments via `attachment=pymax.files.File(...)` in addition to `Photo` and `Video`.
- For inbound polling, adapter code must not assume that `MaxClient.fetch_history()` is ordered `newest -> oldest`; filtering by cursor has to scan the whole returned batch instead of stopping at the first old message.
- `MaxClient` supports live inbound handling through message handlers; in this repository the adapter buffers handler events and the application drains them as the primary `MAX -> Telegram` transport.
- `fetch_history()` remains a fallback catch-up path and should not be used as a high-frequency steady-state polling mechanism for every chat.
- Human-readable titles for MAX dialogs can be resolved as "the participant whose ID differs from chat.owner".
- Background/runtime `start()` paths in this repository are restore-only: if `session.db` is missing or `auth.token` is empty, the adapter raises `AuthError` instead of starting a fresh QR login flow in the background.
- Generic MAX file/document attaches are currently treated in-repo as `type=document` when `attach.type` is `FILE` or `DOCUMENT`, with `attach.url` used as the download source and `attach.file_name`/`filename`/`name`/`title` as filename candidates.
- Self-chat (`chat_id=0`) file messages may arrive as `FileAttach(file_id, name, size, token, type=FILE)` without any direct `url`; in that shape the repository can preserve file semantics and filename, but cannot fetch the binary without additional token-to-download resolution.
- Forwarded / linked MAX messages may expose the actual supported payload under `message.link.message` while the top-level message stays effectively empty (`type=USER`, no text/attaches usable for rendering). Adapter code should preserve top-level sender/time/id metadata, but read content/media metadata from `link.message` when the top level has no renderable content.

## Known Unknowns

The following still need explicit confirmation or stronger documentation:

1. **Session lifecycle details:**
   - What exact events or exceptions indicate expired auth versus transient disconnect?
   - Which parts of the on-disk session are safe to treat as reusable across restarts?

2. **Chat and message model details:**
   - Which fields on chats/messages are stable enough to rely on as long-term identifiers?
   - Which media/message types are supported end-to-end in v1 without fallback text?

3. **Polling and reconnect behavior:**
   - What reconnect/backoff behavior should be considered acceptable for background delivery?
   - Which adapter states should be treated as recoverable versus `reauth_required`?

4. **Operational contract:**
   - Which files inside `MAX_WORK_DIR` are mandatory for restore?
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
