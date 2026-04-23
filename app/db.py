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


def init_app(app):
    """Register close_db as a teardown handler on the Flask app."""
    app.teardown_appcontext(close_db)
    # Schema changes live in migrations/NNN_*.py exclusively; see
    # deploy/MIGRATION_SOP.md. The legacy startup-time _run_migrations was
    # removed in commit introducing migration 008 — all deployments should
    # now run migrate.py as part of the release process.
