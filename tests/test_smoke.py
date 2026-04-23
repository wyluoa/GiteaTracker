"""Smoke test — verifies the test infra itself boots."""


def test_app_fixture_initializes_schema(app, db):
    """The app fixture should have built every schema table + seeded nodes."""
    tables = {r["name"] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )}
    assert "issues" in tables
    assert "users" in tables
    assert "nodes" in tables
    assert "timeline_entries" in tables
    assert "schema_version" in tables
    # Auto-seeded nodes
    count = db.execute("SELECT COUNT(*) AS c FROM nodes").fetchone()["c"]
    assert count == 10


def test_migrations_all_applied(app, db):
    """Fresh DB built from schema.sql should have every migration recorded
    as 'applied' after migrate.py runs (even if idempotent ALTERs skipped)."""
    from pathlib import Path
    mig_dir = Path(__file__).resolve().parent.parent / "migrations"
    expected = [p.name.split("_", 1)[0] for p in sorted(mig_dir.glob("[0-9]*.py"))]
    applied = {r["version"] for r in db.execute("SELECT version FROM schema_version")}
    assert set(expected) <= applied, f"missing: {set(expected) - applied}"


def test_user_fixtures(super_user, manager_user, editor_user, db):
    """Role fixtures should produce users with the right flags."""
    rows = {r["username"]: dict(r) for r in db.execute("SELECT * FROM users")}
    assert rows["super"]["is_super_user"] == 1
    assert rows["super"]["is_manager"] == 0
    assert rows["mgr"]["is_super_user"] == 0
    assert rows["mgr"]["is_manager"] == 1
    assert rows["editor"]["is_super_user"] == 0
    assert rows["editor"]["is_manager"] == 0


def test_login_helper_grants_session(client, super_user, login_as):
    """After login_as(user), a login-required endpoint returns 200."""
    login_as(super_user)
    r = client.get("/tracker")
    assert r.status_code == 200


def test_unauthenticated_redirects(client):
    """No login → /changes is gated — expect 302 to /login."""
    r = client.get("/changes")
    assert r.status_code in (302, 401)


def test_isolated_db_between_tests_part1(db):
    db.execute("INSERT INTO settings (key, value) VALUES ('x', '1')")
    db.commit()


def test_isolated_db_between_tests_part2(db):
    row = db.execute("SELECT value FROM settings WHERE key='x'").fetchone()
    # If DB wasn't isolated, part1 would leak and this would find '1'.
    assert row is None, "DB leaked from previous test — isolation is broken"
