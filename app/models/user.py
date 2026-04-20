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
    db = get_db()
    db.execute("UPDATE users SET last_viewed_at = ? WHERE id = ?", (_now(), user_id))
    db.commit()
