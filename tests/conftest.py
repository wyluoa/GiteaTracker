"""
Pytest fixtures for Gitea Tracker.

Each test gets a fully isolated SQLite DB in pytest's tmp_path. The schema
is loaded from app/schema.sql, then migrate.py runs all pending migrations,
so tests exercise the same code path as a real `init_db.py` install.

Fixtures:
  tmp_db_path      — path to the isolated DB file
  app              — Flask app pointed at the isolated DB
  client           — Flask test client (request/response)
  db               — direct sqlite3 connection for assertions / seeding
  make_user        — factory for creating users of any role
  super_user, manager_user, editor_user  — pre-made users
  login_as         — helper that logs a user in via session (skips password)
  nodes            — list of seeded nodes (A10, A12, ..., MtM)
  sample_issue     — factory for creating an issue quickly
"""
import os
import sqlite3
from pathlib import Path

import bcrypt
import pytest


ROOT = Path(__file__).resolve().parent.parent


# ─── App + DB isolation ────────────────────────────────────────────────

@pytest.fixture
def tmp_db_path(tmp_path):
    """Path to an empty file where we'll build a test DB."""
    return tmp_path / "test.db"


@pytest.fixture
def app(tmp_db_path, tmp_path, monkeypatch):
    """A Flask app wired to an isolated, freshly-migrated DB.

    Uses monkeypatch.setattr on Config so the override unwinds at test
    teardown — no risk of polluting a later test or the dev DB.
    """
    att_dir = tmp_path / "attachments"
    att_dir.mkdir(exist_ok=True)

    # Patch Config BEFORE create_app so app.config reads the test paths.
    from config import Config
    monkeypatch.setattr(Config, "DB_PATH", str(tmp_db_path))
    monkeypatch.setattr(Config, "ATTACHMENT_DIR", str(att_dir))
    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret-not-for-prod")
    monkeypatch.setattr(Config, "BASE_URL", "")

    # Build schema + run all migrations against the test DB.
    schema_sql = (ROOT / "app" / "schema.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(str(tmp_db_path))
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()

    # Apply pending migrations. migrate.run() prints to stdout; capsys in tests
    # can silence that if desired. Running the real migration path means tests
    # will catch a migration that breaks the fresh-DB codepath.
    from migrate import run as run_migrations
    run_migrations()

    # Create the Flask app. create_app() also runs the legacy
    # app.db._run_migrations — harmless here since migrations already ensured
    # the columns exist (idempotent ALTERs).
    from app import create_app
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False  # no-op today, future-proof

    yield flask_app


@pytest.fixture
def client(app):
    """Flask test client — use for HTTP-level assertions."""
    return app.test_client()


@pytest.fixture
def db(tmp_db_path):
    """Direct sqlite3 connection to the test DB — for seeding / assertions
    OUTSIDE the Flask request cycle. Uses Row factory for ergonomic access."""
    conn = sqlite3.connect(str(tmp_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


# ─── User factories ────────────────────────────────────────────────────

def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def make_user(db):
    """Factory: make_user(username, is_super_user=False, is_manager=False)."""
    def _make(username, *, is_super_user=False, is_manager=False,
              display_name=None, password="testpw", status="active",
              email=None):
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        now = _now_iso()
        cur = db.execute(
            """INSERT INTO users (username, email, display_name, password_hash,
                                   status, is_super_user, is_manager,
                                   last_viewed_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (username, email or f"{username}@test.local",
             display_name or username.upper(), pw_hash, status,
             int(is_super_user), int(is_manager), now, now, now),
        )
        db.commit()
        uid = cur.lastrowid
        return {
            "id": uid, "username": username, "password": password,
            "display_name": display_name or username.upper(),
            "is_super_user": is_super_user, "is_manager": is_manager,
        }
    return _make


@pytest.fixture
def super_user(make_user):
    return make_user("super", is_super_user=True)


@pytest.fixture
def manager_user(make_user):
    return make_user("mgr", is_manager=True)


@pytest.fixture
def editor_user(make_user, db):
    """A regular editor with edit rights on every active node via a group."""
    user = make_user("editor")
    # Create "all nodes" group, put user in it, attach every active node.
    cur = db.execute(
        "INSERT INTO groups (name, description, is_active, created_at) VALUES (?, ?, 1, ?)",
        ("all-nodes", "test-only group with all nodes", _now_iso()),
    )
    gid = cur.lastrowid
    db.execute("INSERT INTO user_groups (user_id, group_id) VALUES (?, ?)",
               (user["id"], gid))
    for row in db.execute("SELECT id FROM nodes WHERE is_active = 1"):
        db.execute("INSERT INTO group_nodes (group_id, node_id) VALUES (?, ?)",
                   (gid, row["id"]))
    db.commit()
    return user


# ─── Login helper ──────────────────────────────────────────────────────

@pytest.fixture
def login_as(client):
    """Set session["user_id"] directly — skip the real login form."""
    def _login(user):
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
            sess.permanent = True
        return client
    return _login


# ─── Default data: seed nodes (matches production seed.py layout) ──────

@pytest.fixture(autouse=True)
def seed_nodes(app, db):
    """All tests get the standard 10-node layout automatically.
    Depends on `app` to guarantee schema + migrations ran first."""
    nodes = [
        ("n_a10", "A10", 10),
        ("n_a12", "A12", 20),
        ("n_a14", "A14", 30),
        ("n_n2",  "N2",  40),
        ("n_a16", "A16", 50),
        ("n_n3",  "N3",  60),
        ("n_n4n5", "N4/N5", 70),
        ("n_n6n7", "N6/N7", 80),
        ("n_000", "000",  90),
        ("n_mtm", "MtM", 100),
    ]
    for code, name, order in nodes:
        db.execute(
            """INSERT OR IGNORE INTO nodes (code, display_name, sort_order, is_active)
               VALUES (?, ?, ?, 1)""",
            (code, name, order),
        )
    db.commit()


@pytest.fixture
def nodes(db):
    rows = db.execute(
        "SELECT * FROM nodes WHERE is_active=1 ORDER BY sort_order"
    ).fetchall()
    return [dict(r) for r in rows]


# ─── Issue factory ─────────────────────────────────────────────────────

@pytest.fixture
def sample_issue(db):
    """Factory creating an ongoing issue, timestamped at the current moment.
    Returns its id.

    When testing /changes aggregation, prefer `old_issue` below — a freshly
    created sample_issue has created_at = now, which looks like a new-issue
    event to build_summary and inflates counts."""
    def _make(*, display_number="T001", topic="test topic",
              week_year=2024, week_number=40,
              requestor_name="alice", jira_ticket=None, uat_path=None,
              status="ongoing", created_by_user_id=None):
        now = _now_iso()
        cur = db.execute(
            """INSERT INTO issues
               (display_number, topic, requestor_name,
                week_year, week_number, jira_ticket, uat_path, status,
                created_at, created_by_user_id, updated_at, latest_update_at,
                topic_updated_at, owner_updated_at, jira_updated_at, uat_path_updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (display_number, topic, requestor_name,
             week_year, week_number, jira_ticket, uat_path, status,
             now, created_by_user_id, now, now, now, now, now, now),
        )
        db.commit()
        return cur.lastrowid
    return _make


@pytest.fixture
def old_issue(db, sample_issue):
    """Factory: same as sample_issue but back-dates created_at to the year
    2020 so the issue is NOT seen as new by changes_summary (since=now-1h)."""
    BACKDATE = "2020-01-01T00:00:00+00:00"

    def _make(**kwargs):
        iid = sample_issue(**kwargs)
        db.execute("UPDATE issues SET created_at=? WHERE id=?", (BACKDATE, iid))
        db.commit()
        return iid
    return _make


# ─── Red-line setting helper ───────────────────────────────────────────

@pytest.fixture
def set_red_line(db):
    """Factory: set_red_line(year, week) writes the red-line setting."""
    def _set(year, week):
        db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('red_line_week_year', ?)",
            (str(year),),
        )
        db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('red_line_week_number', ?)",
            (str(week),),
        )
        db.commit()
    return _set
