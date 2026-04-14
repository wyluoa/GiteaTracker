-- Gitea Tracker Schema
-- All datetime fields are ISO 8601 strings (UTC).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    email           TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending/active/disabled
    is_super_user   INTEGER NOT NULL DEFAULT 0,
    last_viewed_at  TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS groups (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,
    description  TEXT,
    is_active    INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_groups (
    user_id   INTEGER NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    group_id  INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, group_id)
);

CREATE TABLE IF NOT EXISTS nodes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL UNIQUE,
    display_name  TEXT NOT NULL,
    sort_order    INTEGER NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS group_nodes (
    group_id  INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    node_id   INTEGER NOT NULL REFERENCES nodes(id)  ON DELETE CASCADE,
    PRIMARY KEY (group_id, node_id)
);

CREATE TABLE IF NOT EXISTS issues (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    display_number        TEXT NOT NULL,
    topic                 TEXT NOT NULL,
    requestor_user_id     INTEGER REFERENCES users(id),
    requestor_name        TEXT,
    owner_user_id         INTEGER REFERENCES users(id),
    week_year             INTEGER NOT NULL,
    week_number           INTEGER NOT NULL,
    jira_ticket           TEXT,
    icv                   TEXT,
    uat_path              TEXT,
    gitea_issue_url       TEXT,
    status                TEXT NOT NULL DEFAULT 'ongoing',  -- ongoing/on_hold/closed
    closed_at             TEXT,
    closed_by_user_id     INTEGER REFERENCES users(id),
    closed_note           TEXT,
    is_deleted            INTEGER NOT NULL DEFAULT 0,
    latest_update_at      TEXT,
    all_nodes_done        INTEGER NOT NULL DEFAULT 0,
    group_label           TEXT,             -- non-week group label (e.g. "強身健體系列")
    created_at            TEXT NOT NULL,
    created_by_user_id    INTEGER REFERENCES users(id),
    updated_at            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status, is_deleted);
CREATE INDEX IF NOT EXISTS idx_issues_week   ON issues(week_year, week_number);
CREATE INDEX IF NOT EXISTS idx_issues_latest ON issues(latest_update_at);

CREATE TABLE IF NOT EXISTS issue_node_states (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id                 INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    node_id                  INTEGER NOT NULL REFERENCES nodes(id),
    state                    TEXT,
    check_in_date            TEXT,
    short_note               TEXT,
    updated_at               TEXT,
    updated_by_user_id       INTEGER REFERENCES users(id),
    updated_by_name_snapshot TEXT,
    UNIQUE (issue_id, node_id)
);

CREATE INDEX IF NOT EXISTS idx_states_issue ON issue_node_states(issue_id);
CREATE INDEX IF NOT EXISTS idx_states_node  ON issue_node_states(node_id, state);

CREATE TABLE IF NOT EXISTS timeline_entries (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id              INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    entry_type            TEXT NOT NULL,  -- state_change/comment/meeting_note
    node_id               INTEGER REFERENCES nodes(id),
    old_state             TEXT,
    new_state             TEXT,
    old_check_in_date     TEXT,
    new_check_in_date     TEXT,
    old_short_note        TEXT,
    new_short_note        TEXT,
    body                  TEXT,
    meeting_week_year     INTEGER,
    meeting_week_number   INTEGER,
    author_user_id        INTEGER REFERENCES users(id),
    author_name_snapshot  TEXT NOT NULL,
    created_at            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_timeline_issue ON timeline_entries(issue_id, created_at);
CREATE INDEX IF NOT EXISTS idx_timeline_type  ON timeline_entries(entry_type);

CREATE TABLE IF NOT EXISTS attachments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timeline_entry_id   INTEGER NOT NULL REFERENCES timeline_entries(id) ON DELETE CASCADE,
    original_filename   TEXT NOT NULL,
    stored_path         TEXT NOT NULL,
    mime_type           TEXT NOT NULL,
    size_bytes          INTEGER NOT NULL,
    created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    used_at     TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id  INTEGER REFERENCES users(id),
    action         TEXT NOT NULL,
    target_type    TEXT,
    target_id      INTEGER,
    details        TEXT,
    created_at     TEXT NOT NULL
);
