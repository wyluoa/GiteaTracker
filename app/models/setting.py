"""Settings model — key-value store."""
from app.db import get_db


def get(key, default=None):
    row = get_db().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set(key, value):
    db = get_db()
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
        (key, value, value),
    )
    db.commit()


def get_red_line():
    """Return (week_year, week_number) or (None, None)."""
    year = get("red_line_week_year")
    week = get("red_line_week_number")
    if year and week:
        return int(year), int(week)
    return None, None
