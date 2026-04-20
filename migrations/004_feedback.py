"""Add feedback table for user bug reports / feature requests / comments.

Submitted by any logged-in user; reviewed and replied to by super users.
"""

SCHEMA_VERSION = "004"
DESCRIPTION = "feedback: add table for user feedback with admin reply"


def up(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS feedback (
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
           )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_feedback_author ON feedback(author_user_id, created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback(status, created_at)"
    )
