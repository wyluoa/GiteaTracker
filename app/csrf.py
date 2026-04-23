"""
Lightweight CSRF protection.

Design:
  - Per-session random token stored in session["_csrf"], created on first read.
  - Unsafe methods (POST/PUT/PATCH/DELETE) must present the token either as
    a form field `csrf_token` OR header `X-CSRFToken`.
  - Token comparison uses secrets.compare_digest (constant time).
  - Token is available in templates as `{{ csrf_token() }}` and in a
    `<meta name="csrf-token">` tag (base.html) for JS/HTMX callers.
  - Endpoints exempted via @csrf_exempt or by name in EXEMPT_ENDPOINTS
    (login, register, password-reset routes — they predate session auth).

Why not Flask-WTF?
  This module only needs `itsdangerous` / `secrets` (both stdlib-adjacent
  dependencies Flask already pulls in). Zero new packages — safer to
  install on restricted corporate PyPI mirrors.
"""
import secrets
from functools import wraps

from flask import current_app, request, session, abort, g


# Endpoints that may receive POSTs before a session/CSRF token exists.
# These must handle their own safety (rate limits / tokenised reset links).
EXEMPT_ENDPOINTS = frozenset({
    "auth.login",
    "auth.register",
    "auth.forgot_password",
    "auth.reset_password",
    "main.healthz",
})

# Methods that mutate state and must carry a CSRF token.
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _get_or_create_token():
    """Return the session's CSRF token, creating one on first call."""
    tok = session.get("_csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["_csrf"] = tok
        session.permanent = True
    return tok


def _submitted_token():
    """Extract the token from form or header (in that priority)."""
    if request.form:
        t = request.form.get("csrf_token")
        if t:
            return t
    return (request.headers.get("X-CSRFToken")
            or request.headers.get("X-CSRF-Token"))


def _is_valid(submitted):
    """Constant-time compare submitted vs session token."""
    if not submitted:
        return False
    expected = session.get("_csrf")
    if not expected:
        return False
    try:
        return secrets.compare_digest(str(submitted), str(expected))
    except Exception:
        return False


def csrf_exempt(view):
    """Decorator — skip CSRF check on this view. Use sparingly."""
    view._csrf_exempt = True
    return view


def _view_is_exempt():
    endpoint = request.endpoint
    if not endpoint:
        return True                                  # 404, static, etc.
    if endpoint in EXEMPT_ENDPOINTS:
        return True
    if endpoint.startswith("static") or endpoint == "static":
        return True
    if endpoint == "flasgger.oauth_redirect":
        return True
    view = current_app.view_functions.get(endpoint)
    if view and getattr(view, "_csrf_exempt", False):
        return True
    return False


def _guard():
    """before_request hook: reject unsafe requests without a valid token."""
    if request.method not in UNSAFE_METHODS:
        return None
    if _view_is_exempt():
        return None
    if current_app.config.get("WTF_CSRF_ENABLED") is False:
        return None                                  # tests may disable
    if not _is_valid(_submitted_token()):
        abort(403, description="CSRF token missing or invalid")


def init_app(app):
    """Register the guard + the `csrf_token()` template helper."""
    app.before_request(_guard)

    @app.context_processor
    def _inject_csrf():
        return {"csrf_token": _get_or_create_token}

    # Make `csrf_exempt` available as `app.csrf_exempt` for convenience.
    app.csrf_exempt = csrf_exempt
