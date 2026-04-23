"""Add field_change support + undo-baseline for mark-as-read.

1) timeline_entries: add field_name / old_field_value / new_field_value so that
   changes to issues.topic/owner/jira/uat_path can be logged with proper
   before→after, symmetric to state_change. (Pre-migration history cannot be
   reconstructed — those stay as cache-column timestamps only.)

2) users: add previous_last_viewed_at so "標記已讀" is undoable — pressing the
   button saves the old value here before overwriting last_viewed_at.

Idempotent: guarded by PRAGMA table_info.
"""

SCHEMA_VERSION = "007"
DESCRIPTION = "timeline_entries: field_change columns; users: previous_last_viewed_at"


def up(conn):
    # timeline_entries
    cur = conn.execute("PRAGMA table_info(timeline_entries)")
    existing = {row[1] for row in cur.fetchall()}
    for col in ("field_name", "old_field_value", "new_field_value"):
        if col not in existing:
            conn.execute(f"ALTER TABLE timeline_entries ADD COLUMN {col} TEXT")

    # users
    cur = conn.execute("PRAGMA table_info(users)")
    existing = {row[1] for row in cur.fetchall()}
    if "previous_last_viewed_at" not in existing:
        conn.execute("ALTER TABLE users ADD COLUMN previous_last_viewed_at TEXT")
