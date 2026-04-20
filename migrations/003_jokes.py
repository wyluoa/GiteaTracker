"""Add jokes table for /fun (meeting warm-up light-story easter egg).

Append-only table. Uses CREATE IF NOT EXISTS / idx so re-runs are no-ops.
"""

SCHEMA_VERSION = "003"
DESCRIPTION = "jokes: add table for meeting warm-up stories (/fun easter egg)"


def up(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS jokes (
             id                    INTEGER PRIMARY KEY AUTOINCREMENT,
             body                  TEXT NOT NULL,
             author_user_id        INTEGER REFERENCES users(id),
             author_name_snapshot  TEXT NOT NULL,
             created_at            TEXT NOT NULL,
             is_deleted            INTEGER NOT NULL DEFAULT 0
           )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jokes_created ON jokes(created_at, is_deleted)"
    )
