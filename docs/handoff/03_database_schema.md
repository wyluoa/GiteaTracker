# 資料表結構草案 (v2)

更動自 v1:
- `issues` 新增 `requestor_user_id` + `requestor_name` 雙欄位
- `issue_node_states` 新增 `short_note` 欄位

---

所有表格使用 SQLite,時間欄位統一 ISO 8601 UTC 字串。

## users

```sql
CREATE TABLE users (
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
```

## groups

```sql
CREATE TABLE groups (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,
    description  TEXT,
    created_at   TEXT NOT NULL
);
```

## user_groups

```sql
CREATE TABLE user_groups (
    user_id   INTEGER NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    group_id  INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, group_id)
);
```

## nodes

```sql
CREATE TABLE nodes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL UNIQUE,      -- 固定內部 ID, 例如 'n_a10'
    display_name  TEXT NOT NULL,             -- 可改, 例如 'A10' 或 'N4/N5'
    sort_order    INTEGER NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1
);
```

## group_nodes

```sql
CREATE TABLE group_nodes (
    group_id  INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    node_id   INTEGER NOT NULL REFERENCES nodes(id)  ON DELETE CASCADE,
    PRIMARY KEY (group_id, node_id)
);
```

## issues

```sql
CREATE TABLE issues (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    display_number        TEXT NOT NULL,
    topic                 TEXT NOT NULL,

    -- Requestor 雙欄位
    requestor_user_id     INTEGER REFERENCES users(id),  -- 可 null
    requestor_name        TEXT,                           -- 顯示優先用這個

    owner_user_id         INTEGER REFERENCES users(id),

    week_year             INTEGER NOT NULL,
    week_number           INTEGER NOT NULL,

    jira_ticket           TEXT,
    icv                   TEXT,
    uat_path              TEXT,
    gitea_issue_url       TEXT,

    status                TEXT NOT NULL DEFAULT 'ongoing', -- ongoing/on_hold/closed
    closed_at             TEXT,
    closed_by_user_id     INTEGER REFERENCES users(id),
    closed_note           TEXT,
    is_deleted            INTEGER NOT NULL DEFAULT 0,

    -- 衍生 cache
    latest_update_at      TEXT,
    all_nodes_done        INTEGER NOT NULL DEFAULT 0,

    created_at            TEXT NOT NULL,
    created_by_user_id    INTEGER REFERENCES users(id),
    updated_at            TEXT NOT NULL
);

CREATE INDEX idx_issues_status  ON issues(status, is_deleted);
CREATE INDEX idx_issues_week    ON issues(week_year, week_number);
CREATE INDEX idx_issues_latest  ON issues(latest_update_at);
```

## issue_node_states

```sql
CREATE TABLE issue_node_states (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id                 INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    node_id                  INTEGER NOT NULL REFERENCES nodes(id),
    state                    TEXT,                  -- done/developing/uat/uat_done/unneeded/tbd/NULL
    check_in_date            TEXT,                  -- YYYY-MM-DD
    short_note               TEXT,                  -- 短註記, 在 cell 下方小字顯示
    updated_at               TEXT,
    updated_by_user_id       INTEGER REFERENCES users(id),
    updated_by_name_snapshot TEXT,
    UNIQUE (issue_id, node_id)
);

CREATE INDEX idx_states_issue  ON issue_node_states(issue_id);
CREATE INDEX idx_states_node   ON issue_node_states(node_id, state);
```

## timeline_entries

```sql
CREATE TABLE timeline_entries (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id              INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    entry_type            TEXT NOT NULL,      -- state_change/comment/meeting_note
    node_id               INTEGER REFERENCES nodes(id),  -- 只有 state_change 用到
    old_state             TEXT,
    new_state             TEXT,
    old_check_in_date     TEXT,
    new_check_in_date     TEXT,
    old_short_note        TEXT,
    new_short_note        TEXT,
    body                  TEXT,               -- 文字說明 / 留言內容
    meeting_week_year     INTEGER,            -- 只有 meeting_note 用到
    meeting_week_number   INTEGER,
    author_user_id        INTEGER REFERENCES users(id),
    author_name_snapshot  TEXT NOT NULL,
    created_at            TEXT NOT NULL
);

CREATE INDEX idx_timeline_issue ON timeline_entries(issue_id, created_at);
CREATE INDEX idx_timeline_type  ON timeline_entries(entry_type);
```

## attachments

```sql
CREATE TABLE attachments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timeline_entry_id   INTEGER NOT NULL REFERENCES timeline_entries(id) ON DELETE CASCADE,
    original_filename   TEXT NOT NULL,
    stored_path         TEXT NOT NULL,
    mime_type           TEXT NOT NULL,
    size_bytes          INTEGER NOT NULL,
    created_at          TEXT NOT NULL
);
```

## settings

```sql
CREATE TABLE settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

-- 預期的 key:
-- red_line_week_year, red_line_week_number
-- smtp_host / smtp_port / smtp_user / smtp_password / smtp_from_email
-- attachment_max_mb
-- session_hours
```

## password_reset_tokens

```sql
CREATE TABLE password_reset_tokens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    used_at     TEXT,
    created_at  TEXT NOT NULL
);
```

## audit_log

```sql
CREATE TABLE audit_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id  INTEGER REFERENCES users(id),
    action         TEXT NOT NULL,
                   -- create_user/approve_user/disable_user
                   -- create_group/assign_node
                   -- close_issue/reopen_issue/delete_issue
                   -- set_red_line/batch_update
    target_type    TEXT,
    target_id      INTEGER,
    details        TEXT,         -- JSON
    created_at     TEXT NOT NULL
);
```

---

## 關鍵設計說明

### Requestor 雙欄位
- 新題目時,super user 可從下拉選現有 user (自動填 user_id + 帶 display_name 到 name 欄位),也可直接打字 (只填 name)
- 顯示永遠優先用 `requestor_name`,避免改名 / 離職影響歷史
- 舊資料匯入時全部走自由文字,`requestor_user_id` 留 null

### short_note vs timeline
- `short_note` 放「持續性的現況描述」,例如「等廠商 3/15 回覆」、「待 spec 確認」,會持續顯示在 cell 下方
- Timeline 放「一次性的事件」,例如狀態變更、會議討論、補充說明
- 兩者互補,不是取代關係

### state_change 記錄欄位
- 除了 old/new state,也記 old/new check_in_date 和 short_note
- 這樣任何 cell 層級的修改都能在 timeline 看到完整 diff

### name_snapshot
- user_id 負責連結,name_snapshot 負責顯示
- 即使帳號停用或改名,歷史紀錄仍顯示當時名字
