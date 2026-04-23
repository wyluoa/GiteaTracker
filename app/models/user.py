"""User model — CRUD + authentication helpers."""
from datetime import datetime, timezone

import bcrypt

from app.db import get_db


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_user(username, email, display_name, password, status="pending", is_super_user=False):
    db = get_db()
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    now = _now()
    cur = db.execute(
        """INSERT INTO users (username, email, display_name, password_hash,
                              status, is_super_user, last_viewed_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (username, email, display_name, password_hash, status, int(is_super_user), now, now, now),
    )
    db.commit()
    return cur.lastrowid


def create_user_raw(username, email, display_name, password_hash, status="pending", is_super_user=False):
    """Insert a user with a pre-hashed password (for seed/import)."""
    db = get_db()
    now = _now()
    cur = db.execute(
        """INSERT INTO users (username, email, display_name, password_hash,
                              status, is_super_user, last_viewed_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (username, email, display_name, password_hash, status, int(is_super_user), now, now, now),
    )
    db.commit()
    return cur.lastrowid


def get_by_id(user_id):
    return get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_by_username(username):
    return get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def verify_password(user_row, password):
    if user_row is None:
        return False
    return bcrypt.checkpw(password.encode(), user_row["password_hash"].encode())


def update_last_viewed(user_id):
    """Mark-as-read: advance last_viewed_at, preserving the prior value so
    the user can undo the mark-as-read from the /changes page."""
    db = get_db()
    prev = db.execute(
        "SELECT last_viewed_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    prev_val = prev["last_viewed_at"] if prev else None
    db.execute(
        "UPDATE users SET previous_last_viewed_at = ?, last_viewed_at = ? WHERE id = ?",
        (prev_val, _now(), user_id),
    )
    db.commit()


def undo_last_viewed(user_id):
    """Revert last_viewed_at to previous_last_viewed_at (one-step undo).
    Returns True on success, False if there was nothing to undo."""
    db = get_db()
    row = db.execute(
        "SELECT previous_last_viewed_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not row or not row["previous_last_viewed_at"]:
        return False
    db.execute(
        "UPDATE users SET last_viewed_at = ?, previous_last_viewed_at = NULL WHERE id = ?",
        (row["previous_last_viewed_at"], user_id),
    )
    db.commit()
    return True
