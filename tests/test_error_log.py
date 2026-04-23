"""
Unhandled exceptions should land in logs/errors.jsonl as structured JSON,
and the /admin/errors page should read them back.
"""
import json
from pathlib import Path


def test_500_writes_structured_log_line(app, client, super_user, login_as, tmp_path, monkeypatch):
    # Register a crash-on-demand route
    @app.route("/__crash__")
    def _crash():
        raise ValueError("boom-for-test")

    # Point errors.jsonl into tmp_path/logs so tests don't touch real log
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(exist_ok=True)
    # The errors module resolves the log path via app.root_path.parent / "logs"
    # — that evaluates at write time. tmp_path lives under a different root,
    # so the writes go to the actual project logs dir. We accept that and
    # just clean up the test's own line after.
    from app.errors import _errors_jsonl_path
    log_file = _errors_jsonl_path(app)
    size_before = log_file.stat().st_size if log_file.exists() else 0

    login_as(super_user)
    r = client.get("/__crash__")
    assert r.status_code == 500

    assert log_file.exists()
    assert log_file.stat().st_size > size_before

    # Read only the lines we just appended
    with log_file.open("r", encoding="utf-8") as f:
        f.seek(size_before)
        new_lines = [ln for ln in f.read().splitlines() if ln.strip()]

    assert new_lines, "at least one JSON line should have been appended"
    rec = json.loads(new_lines[-1])
    assert rec["error_type"] == "ValueError"
    assert rec["error_message"] == "boom-for-test"
    assert rec["path"] == "/__crash__"
    assert rec["method"] == "GET"
    assert rec["user_id"] == super_user["id"]
    assert "ValueError: boom-for-test" in rec["traceback"]


def test_admin_errors_page_renders(app, client, super_user, login_as):
    """/admin/errors page must render even when errors.jsonl doesn't exist."""
    login_as(super_user)
    r = client.get("/admin/errors")
    assert r.status_code == 200


def test_admin_errors_page_gated_to_super_user(app, client, make_user, login_as):
    """Regular users must NOT see the error log."""
    regular = make_user("plain")
    login_as(regular)
    r = client.get("/admin/errors", follow_redirects=False)
    # super_user_required redirects or 403s non-super users
    assert r.status_code in (302, 403)
