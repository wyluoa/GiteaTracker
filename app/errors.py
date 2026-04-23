"""Custom error handlers + structured error log for post-incident review.

Writes each unhandled 500 to logs/errors.jsonl (one JSON object per line).
A log file makes incidents recoverable without needing an external
service like Sentry, which would require docker / network egress that
corporate restrictions often block.

An admin UI at /admin/errors reads this file — see app/routes/admin.py.
"""
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

from flask import render_template, request, session, g


def _errors_jsonl_path(app):
    """logs/errors.jsonl next to app.log. Ensure the dir exists."""
    root = Path(app.root_path).parent
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "errors.jsonl"


def _log_exception(app, exc):
    """Append a JSON line describing the exception. Best-effort — any
    failure here is swallowed so we never replace a 500 with another 500."""
    try:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "path": request.path,
            "method": request.method,
            "endpoint": request.endpoint,
            "user_id": session.get("user_id"),
            "user_name": (g.current_user["display_name"]
                          if getattr(g, "current_user", None) else None),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc(),
            "remote_addr": request.headers.get("X-Forwarded-For")
                           or request.remote_addr,
        }
        path = _errors_jsonl_path(app)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Don't let telemetry crash the error path.
        pass


def register_error_handlers(app):
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(e):
        _log_exception(app, e)
        return render_template("errors/500.html"), 500

    # Catch-all for unhandled exceptions (werkzeug raises these BEFORE
    # they become 500 responses in DEBUG mode, so the 500 handler alone
    # misses them). Only log — let Flask's default behavior produce the
    # response.
    @app.errorhandler(Exception)
    def any_unhandled(e):
        # 4xx HTTPException subclasses go back through their own handlers
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e
        _log_exception(app, e)
        return render_template("errors/500.html"), 500
