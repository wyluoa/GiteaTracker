"""Consolidate legacy in-app migrations into the migrations/ system.

Before this migration, `app/db.py::_run_migrations` ran on every app
startup and added two columns (`pending_close` on issues, `is_manager`
on users) if missing. That meant migrations lived in TWO places:

  - migrations/NNN_*.py   — the real system (this folder)
  - app/db.py             — legacy inline adds on startup

The dual system is a tech-debt landmine: easy for a new contributor to
add the wrong kind of migration, and the startup-time ALTER slows every
boot by the price of a PRAGMA + possible ALTER.

This migration:
  1. Asserts the two legacy columns exist (they SHOULD — the legacy
     _run_migrations has been running on every startup for months).
     If they don't, re-add them so no existing installation breaks.
  2. The companion commit removes app/db.py::_run_migrations entirely.

Idempotent: checks before adding. Also tolerates a hypothetical fresh
install that ran schema.sql (where both columns are declared) before
running this migration.
"""

SCHEMA_VERSION = "008"
DESCRIPTION = "consolidate: ensure legacy cols (issues.pending_close, users.is_manager) exist"


def up(conn):
    issue_cols = {r[1] for r in conn.execute("PRAGMA table_info(issues)").fetchall()}
    if "pending_close" not in issue_cols:
        conn.execute(
            "ALTER TABLE issues ADD COLUMN pending_close INTEGER NOT NULL DEFAULT 0"
        )

    user_cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "is_manager" not in user_cols:
        conn.execute(
            "ALTER TABLE users ADD COLUMN is_manager INTEGER NOT NULL DEFAULT 0"
        )
