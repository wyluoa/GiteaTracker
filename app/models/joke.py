"""Joke model — CRUD for /fun easter-egg page."""
from datetime import datetime, timezone
import random

from app.db import get_db


def _now():
    return datetime.now(timezone.utc).isoformat()


def create(*, body, author_user_id, author_name_snapshot):
    db = get_db()
    cur = db.execute(
        """INSERT INTO jokes (body, author_user_id, author_name_snapshot, created_at)
           VALUES (?, ?, ?, ?)""",
        (body, author_user_id, author_name_snapshot, _now()),
    )
    db.commit()
    return cur.lastrowid


def list_all():
    return get_db().execute(
        "SELECT * FROM jokes WHERE is_deleted = 0 ORDER BY created_at DESC"
    ).fetchall()


def get_random():
    """Return one random non-deleted joke, or None if the table is empty."""
    rows = list_all()
    return random.choice(rows) if rows else None


def get_by_id(joke_id):
    return get_db().execute(
        "SELECT * FROM jokes WHERE id = ? AND is_deleted = 0", (joke_id,)
    ).fetchone()


def soft_delete(joke_id):
    db = get_db()
    db.execute("UPDATE jokes SET is_deleted = 1 WHERE id = ?", (joke_id,))
    db.commit()


def count():
    return get_db().execute(
        "SELECT COUNT(*) FROM jokes WHERE is_deleted = 0"
    ).fetchone()[0]
