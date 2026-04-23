"""
CSRF protection:
  - POSTs without a token are 403
  - POSTs with a valid token succeed
  - GET requests are unaffected
  - Exempt endpoints (login, register, password-reset) work without token
  - Token is available as {{ csrf_token() }} in templates
  - Token from session matches the one rendered
"""
import pytest


@pytest.fixture
def csrf_app(tmp_db_path, tmp_path, monkeypatch):
    """A Flask app with CSRF ENABLED (default fixture disables it for other
    tests that don't care about CSRF)."""
    from config import Config
    from pathlib import Path
    import sqlite3

    att_dir = tmp_path / "attachments"
    att_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(Config, "DB_PATH", str(tmp_db_path))
    monkeypatch.setattr(Config, "ATTACHMENT_DIR", str(att_dir))
    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret-not-for-prod")
    monkeypatch.setattr(Config, "BASE_URL", "")

    ROOT = Path(__file__).resolve().parent.parent
    schema = (ROOT / "app" / "schema.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(str(tmp_db_path))
    conn.executescript(schema); conn.commit(); conn.close()

    from migrate import run as run_migrations
    run_migrations()

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    # NOTE: do NOT disable WTF_CSRF_ENABLED here — this fixture exercises the
    # real guard. Other tests use the conftest `app` fixture which disables it.
    app.config["WTF_CSRF_ENABLED"] = True
    return app


@pytest.fixture
def csrf_client(csrf_app):
    return csrf_app.test_client()


def _login_via_session(client, user_id):
    with client.session_transaction() as s:
        s["user_id"] = user_id
        s.permanent = True


# ─── 403 when token missing ────────────────────────────────────────────

def test_post_without_token_is_rejected(csrf_app, csrf_client, db, make_user):
    user = make_user("someone")
    _login_via_session(csrf_client, user["id"])

    r = csrf_client.post("/mark_all_read")
    assert r.status_code == 403


def test_post_with_wrong_token_is_rejected(csrf_app, csrf_client, db, make_user):
    user = make_user("someone")
    _login_via_session(csrf_client, user["id"])

    # Submit a token that doesn't match session's
    r = csrf_client.post("/mark_all_read", data={"csrf_token": "garbage-token"})
    assert r.status_code == 403


# ─── Success when token is valid ───────────────────────────────────────

def test_post_with_valid_token_succeeds(csrf_app, csrf_client, db, make_user):
    user = make_user("someone")
    _login_via_session(csrf_client, user["id"])

    # Seed a token into the session directly + read it back
    with csrf_client.session_transaction() as s:
        s["_csrf"] = "seed-token-value"

    r = csrf_client.post("/mark_all_read", data={"csrf_token": "seed-token-value"})
    # mark_all_read redirects on success
    assert r.status_code in (200, 302)


def test_post_with_valid_header_token_succeeds(csrf_app, csrf_client, db, make_user):
    user = make_user("someone")
    _login_via_session(csrf_client, user["id"])

    with csrf_client.session_transaction() as s:
        s["_csrf"] = "header-token-value"

    r = csrf_client.post("/mark_all_read",
                         headers={"X-CSRFToken": "header-token-value"})
    assert r.status_code in (200, 302)


# ─── Safe methods unaffected ───────────────────────────────────────────

def test_get_requests_unaffected(csrf_app, csrf_client, db, make_user):
    user = make_user("someone")
    _login_via_session(csrf_client, user["id"])
    r = csrf_client.get("/tracker")
    assert r.status_code == 200


# ─── Exempt endpoints ──────────────────────────────────────────────────

def test_login_post_exempt(csrf_app, csrf_client, db, make_user):
    """Login must accept POST without a session token (user has no session yet)."""
    make_user("someuser", password="testpw")
    # No CSRF token provided — must still be processed by the auth route.
    # Bad password → 200 with error flash. The point is we DON'T get 403.
    r = csrf_client.post("/login",
                         data={"username": "someuser", "password": "wrong"})
    assert r.status_code != 403


def test_healthz_exempt(csrf_app, csrf_client):
    # healthz is normally GET; exempting it covers any future POST probe.
    r = csrf_client.get("/healthz")
    assert r.status_code == 200


# ─── Template helper ───────────────────────────────────────────────────

def test_csrf_token_available_in_templates(csrf_app, csrf_client, db, make_user):
    """Login page renders and must contain a csrf_token hidden input."""
    r = csrf_client.get("/login")
    assert r.status_code == 200
    body = r.data.decode()
    assert "csrf_token" in body, "login page should include csrf_token hidden input"


def test_rendered_token_matches_session(csrf_app, csrf_client, db, make_user):
    """The token baked into the page must match what's in session."""
    r = csrf_client.get("/login")
    import re
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.data.decode())
    assert m, "csrf_token hidden input not found in login page"
    rendered = m.group(1)
    with csrf_client.session_transaction() as s:
        assert s.get("_csrf") == rendered
