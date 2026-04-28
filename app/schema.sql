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
    is_manager      INTEGER NOT NULL DEFAULT 0,
    last_viewed_at  TEXT,
    previous_last_viewed_at TEXT,
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
    -- NAMING NOTE (do not be misled by the column names):
    -- `requestor_name` actually stores the issue OWNER (developer/assignee) — the
    -- Excel "Owner" column is imported into this field. The tracker UI's "Owner"
    -- column reads `requestor_name`. Schema name is historical baggage from an
    -- early design that planned a separate requestor/owner split; that split was
    -- never implemented. `owner_user_id` exists but is always NULL (no UI ever
    -- writes to it). Treat `requestor_name` as the canonical Owner field.
    requestor_user_id     INTEGER REFERENCES users(id),  -- unused, always NULL
    requestor_name        TEXT,                          -- ACTUAL OWNER (developer) — see note above
    owner_user_id         INTEGER REFERENCES users(id),  -- unused, always NULL — reserved for future user-linked owner
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
    pending_close         INTEGER NOT NULL DEFAULT 0,       -- Excel import suggested close; admin confirms manually
    is_deleted            INTEGER NOT NULL DEFAULT 0,
    latest_update_at      TEXT,
    all_nodes_done        INTEGER NOT NULL DEFAULT 0,
    group_label           TEXT,             -- non-week group label (e.g. "強身健體系列")
    created_at            TEXT NOT NULL,
    created_by_user_id    INTEGER REFERENCES users(id),
    updated_at            TEXT NOT NULL,
    -- Per-field update timestamps for tracker highlight (yellow diff vs. user's last_viewed_at).
    topic_updated_at      TEXT,
    owner_updated_at      TEXT,
    jira_updated_at       TEXT,
    uat_path_updated_at   TEXT
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
    entry_type            TEXT NOT NULL,  -- state_change/comment/meeting_note/field_change
    node_id               INTEGER REFERENCES nodes(id),
    old_state             TEXT,
    new_state             TEXT,
    old_check_in_date     TEXT,
    new_check_in_date     TEXT,
    old_short_note        TEXT,
    new_short_note        TEXT,
    -- Used when entry_type = 'field_change' (topic/owner/jira/uat_path).
    field_name            TEXT,
    old_field_value       TEXT,
    new_field_value       TEXT,
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

-- Weekly trend data (manually entered via Admin)
CREATE TABLE IF NOT EXISTS weekly_trend_data (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    week_year     INTEGER NOT NULL,
    week_number   INTEGER NOT NULL,
    cnt_uat       INTEGER NOT NULL DEFAULT 0,
    cnt_tbd       INTEGER NOT NULL DEFAULT 0,
    cnt_dev       INTEGER NOT NULL DEFAULT 0,
    cnt_close     INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT,
    UNIQUE (week_year, week_number)
);

-- Jokes / light stories for meeting warm-ups (accessed via easter-egg /fun)
CREATE TABLE IF NOT EXISTS jokes (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    body                  TEXT NOT NULL,
    author_user_id        INTEGER REFERENCES users(id),
    author_name_snapshot  TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    is_deleted            INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_jokes_created ON jokes(created_at, is_deleted);

-- User feedback: bug reports, feature requests, general comments
CREATE TABLE IF NOT EXISTS feedback (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    author_user_id          INTEGER NOT NULL REFERENCES users(id),
    author_name_snapshot    TEXT NOT NULL,
    category                TEXT NOT NULL,                -- bug / feature / other
    body                    TEXT NOT NULL,
    status                  TEXT NOT NULL DEFAULT 'new',  -- new / reviewed / resolved
    admin_reply_body        TEXT,
    admin_reply_at          TEXT,
    admin_reply_by_user_id  INTEGER REFERENCES users(id),
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_feedback_author ON feedback(author_user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback(status, created_at);
