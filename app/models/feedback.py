"""Feedback model — user bug reports / feature requests / comments.

Submitted by any logged-in user, reviewed + optionally replied by super users.
"""
from datetime import datetime, timezone

from app.db import get_db


VALID_CATEGORIES = ("bug", "feature", "other")
VALID_STATUSES = ("new", "reviewed", "resolved")


def _now():
    return datetime.now(timezone.utc).isoformat()


def create(*, author_user_id, author_name_snapshot, category, body):
    if category not in VALID_CATEGORIES:
        category = "other"
    now = _now()
    db = get_db()
    cur = db.execute(
        """INSERT INTO feedback
           (author_user_id, author_name_snapshot, category, body,
            status, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'new', ?, ?)""",
        (author_user_id, author_name_snapshot, category, body, now, now),
    )
    db.commit()
    return cur.lastrowid


def list_by_author(author_user_id):
    return get_db().execute(
        "SELECT * FROM feedback WHERE author_user_id = ? ORDER BY created_at DESC",
        (author_user_id,),
    ).fetchall()


def list_all(status=None, category=None):
    sql = "SELECT * FROM feedback WHERE 1=1"
    params = []
    if status and status in VALID_STATUSES:
        sql += " AND status = ?"
        params.append(status)
    if category and category in VALID_CATEGORIES:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY created_at DESC"
    return get_db().execute(sql, params).fetchall()


def get_by_id(feedback_id):
    return get_db().execute(
        "SELECT * FROM feedback WHERE id = ?", (feedback_id,)
    ).fetchone()


def update_status(feedback_id, status):
    if status not in VALID_STATUSES:
        return
    db = get_db()
    db.execute(
        "UPDATE feedback SET status = ?, updated_at = ? WHERE id = ?",
        (status, _now(), feedback_id),
    )
    db.commit()


def add_admin_reply(feedback_id, reply_body, reply_user_id):
    now = _now()
    db = get_db()
    db.execute(
        """UPDATE feedback SET
             admin_reply_body = ?,
             admin_reply_at = ?,
             admin_reply_by_user_id = ?,
             status = CASE WHEN status = 'new' THEN 'reviewed' ELSE status END,
             updated_at = ?
           WHERE id = ?""",
        (reply_body, now, reply_user_id, now, feedback_id),
    )
    db.commit()


def count_by_status():
    """Return {'new': N, 'reviewed': M, 'resolved': K}."""
    rows = get_db().execute(
        "SELECT status, COUNT(*) as c FROM feedback GROUP BY status"
    ).fetchall()
    out = {s: 0 for s in VALID_STATUSES}
    for r in rows:
        out[r["status"]] = r["c"]
    return out
