# Topic Inbound Mute Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task.

**Goal:** Add persistent per-topic inbound mute commands and automatically mute MAX channels whose membership is explicitly absent.

**Architecture:** Persist `inbound_enabled` on `telegram_topics`, expose it through the repository and a focused application service, and enforce it in every inbound path before history or Telegram delivery. Extend the MAX client port with a targeted chat-state lookup used by reconcile only for existing topics missing from the current chat list.

**Tech Stack:** Python 3.13+, aiogram, Pydantic, aiosqlite, PyMax 2.3.1, pytest, Ruff, Pyright.

---

### Task 1: Persist topic inbound state

**Files:**
- Modify: `src/domain/chats/topic.py`
- Modify: `src/application/ports/repositories.py`
- Modify: `src/infrastructure/persistence/schema.py`
- Modify: `src/infrastructure/persistence/init.py`
- Modify: `src/infrastructure/persistence/repositories.py`
- Test: `tests/infrastructure/test_chats_integration.py`

1. Write failing tests for default enabled state, scoped mute updates, and schema upgrade.
2. Run the focused persistence tests and verify RED.
3. Add the model field, safe additive migration, repository reads, and scoped update.
4. Run the focused persistence tests and verify GREEN.

### Task 2: Add command use cases and Telegram handlers

**Files:**
- Create: `src/application/topics/__init__.py`
- Create: `src/application/topics/mute.py`
- Modify: `src/interface/telegram_handlers/handlers.py`
- Modify: `src/main.py`
- Test: `tests/interface/test_handlers.py`
- Test: `tests/application/test_topic_mute.py`

1. Write failing application and handler tests for mute, unmute, outside-topic, unknown-topic, and user isolation behavior.
2. Run the focused tests and verify RED.
3. Implement the application service, command handlers, dependency wiring, and bot command registration.
4. Run the focused tests and verify GREEN.

### Task 3: Enforce mute in inbound synchronization

**Files:**
- Modify: `src/application/routing/inbound.py`
- Test: `tests/application/test_inbound.py`

1. Write failing tests proving muted live messages are ignored and muted catch-up topics do not call MAX history.
2. Run the focused inbound tests and verify RED.
3. Add early mute checks to live and history paths.
4. Run the focused inbound tests and verify GREEN.

### Task 4: Detect confirmed channel departure

**Files:**
- Modify: `src/application/ports/clients.py`
- Modify: `src/infrastructure/max/adapter.py`
- Modify: `src/application/reconcile/service.py`
- Test: `tests/infrastructure/test_max_adapter.py`
- Test: `tests/application/test_reconcile.py`

1. Write failing adapter and reconcile tests for subscribed, unsubscribed, failed lookup, and manual-mute preservation behavior.
2. Run the focused tests and verify RED.
3. Add targeted chat-state normalization and reconcile auto-mute.
4. Preserve mute through forced topic recreation and skip muted backfill.
5. Run the focused tests and verify GREEN.

### Task 5: Document and verify

**Files:**
- Modify: `README.md`
- Modify: `docs/maxapi-python-contract.md`
- Move: `docs/exec-plans/active/MLB-028-topic-inbound-mute.md` to `docs/exec-plans/completed/MLB-028-topic-inbound-mute.md`

1. Document commands, persistence, and the verified MAX channel-membership signal.
2. Run focused tests, then `just check`, `just arch-test`, and `git diff --check`.
3. Inspect the diff and scan it for secrets.
4. Move the completed execution plan and commit all relevant files with a clean Conventional Commit message.

### Task 6: Resume without muted backlog

**Files:**
- Modify: `src/domain/chats/topic.py`
- Modify: `src/infrastructure/persistence/schema.py`
- Modify: `src/infrastructure/persistence/init.py`
- Modify: `src/infrastructure/persistence/repositories.py`
- Modify: `src/application/routing/inbound.py`
- Test: `tests/infrastructure/test_chats_integration.py`
- Test: `tests/application/test_inbound.py`

1. Write failing tests for the persisted unmute boundary and history filtering.
2. Store `inbound_since_ms` when inbound delivery is re-enabled.
3. Skip older history messages while advancing the cursor and deliver only new messages.
4. Run focused tests and the full verification suite.
