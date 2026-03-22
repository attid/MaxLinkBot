"""SQLite schema for MaxLinkBot v1."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS telegram_users (
    telegram_user_id INTEGER PRIMARY KEY,
    created_at       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_bindings (
    telegram_user_id   INTEGER PRIMARY KEY
                            REFERENCES telegram_users(telegram_user_id),
    max_session_data  TEXT    NOT NULL,
    status             TEXT    NOT NULL
                            CHECK (status IN ('active', 'reauth_required', 'disabled')),
    created_at         INTEGER NOT NULL,
    updated_at         INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS max_chats (
    max_chat_id                 TEXT PRIMARY KEY,
    binding_telegram_user_id     INTEGER NOT NULL
                                    REFERENCES user_bindings(telegram_user_id),
    title                        TEXT,
    chat_type                    TEXT NOT NULL DEFAULT 'personal',
    UNIQUE (max_chat_id, binding_telegram_user_id)
);

CREATE TABLE IF NOT EXISTS telegram_topics (
    telegram_topic_id      INTEGER PRIMARY KEY,
    telegram_user_id       INTEGER NOT NULL
                               REFERENCES user_bindings(telegram_user_id),
    max_chat_id            TEXT    NOT NULL
                               REFERENCES max_chats(max_chat_id),
    UNIQUE (telegram_user_id, max_chat_id)
);

CREATE TABLE IF NOT EXISTS message_links (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    max_message_id      TEXT,
    telegram_message_id  INTEGER,
    telegram_user_id     INTEGER NOT NULL
                             REFERENCES user_bindings(telegram_user_id),
    max_chat_id         TEXT    NOT NULL
                             REFERENCES max_chats(max_chat_id),
    direction           TEXT    NOT NULL
                             CHECK (direction IN ('max_to_telegram', 'telegram_to_max')),
    delivered_at        INTEGER NOT NULL,
    UNIQUE (max_message_id, direction, max_chat_id)
);

CREATE TABLE IF NOT EXISTS sync_cursors (
    max_chat_id                 TEXT PRIMARY KEY,
                                -- references max_chats(max_chat_id),
    binding_telegram_user_id    INTEGER NOT NULL
                                    REFERENCES user_bindings(telegram_user_id),
    last_max_message_id         TEXT    NOT NULL,
    updated_at                  INTEGER NOT NULL,
    UNIQUE (max_chat_id, binding_telegram_user_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id  INTEGER NOT NULL
                          REFERENCES user_bindings(telegram_user_id),
    event_type        TEXT    NOT NULL,
    detail            TEXT    NOT NULL,
    created_at        INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_max_chats_owner
    ON max_chats(binding_telegram_user_id);

CREATE INDEX IF NOT EXISTS idx_topics_owner
    ON telegram_topics(telegram_user_id);

CREATE INDEX IF NOT EXISTS idx_message_links_owner
    ON message_links(telegram_user_id);

CREATE INDEX IF NOT EXISTS idx_audit_events_owner
    ON audit_events(telegram_user_id);
"""
