"""
SQLite connection helper.

Uses Flask's `g` to ensure one connection per request, with row_factory set to
sqlite3.Row so we can access columns by name.
"""
import sqlite3
from flask import g, current_app


def get_db():
    """Get the SQLite connection for the current request."""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DB_PATH"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    """Close the connection at the end of the request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _run_migrations(app):
    """Lightweight column-add migrations for existing DBs.

    Keep idempotent. New installs run schema.sql and already have these columns.
    """
    conn = sqlite3.connect(app.config["DB_PATH"])
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(issues)").fetchall()}
        if "pending_close" not in cols:
            conn.execute(
                "ALTER TABLE issues ADD COLUMN pending_close INTEGER NOT NULL DEFAULT 0"
            )
            conn.commit()
    finally:
        conn.close()


def init_app(app):
    """Register close_db as a teardown handler on the Flask app."""
    app.teardown_appcontext(close_db)
    _run_migrations(app)
