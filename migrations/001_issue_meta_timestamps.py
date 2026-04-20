"""Add per-field update timestamps on issues for tracker column highlights.

Adds 4 columns to issues: topic_updated_at, owner_updated_at, jira_updated_at,
uat_path_updated_at. Existing rows are backfilled with the current updated_at
so the baseline is "last modified at whatever updated_at says".

Idempotent: checks PRAGMA table_info before ALTER, so re-running is safe even
on a DB where the old in-place migration (previously inside init_db.py) already
added these columns.
"""

SCHEMA_VERSION = "001"
DESCRIPTION = "issues: add topic/owner/jira/uat_path _updated_at columns"

NEW_COLS = [
    "topic_updated_at",
    "owner_updated_at",
    "jira_updated_at",
    "uat_path_updated_at",
]


def up(conn):
    cur = conn.execute("PRAGMA table_info(issues)")
    existing = {row[1] for row in cur.fetchall()}
    for col in NEW_COLS:
        if col not in existing:
            conn.execute(f"ALTER TABLE issues ADD COLUMN {col} TEXT")
            conn.execute(
                f"UPDATE issues SET {col} = updated_at WHERE {col} IS NULL"
            )
