"""
Main routes — placeholder for Phase 0.

Real routes will be added in later phases.
"""
import sqlite3
from pathlib import Path
from flask import Blueprint, render_template, current_app
from app.db import get_db

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    """Phase 0 placeholder homepage that also reports DB / asset health."""
    db_status = _check_db()
    return render_template(
        "index.html",
        db_status=db_status,
        db_path=current_app.config["DB_PATH"],
    )


@bp.route("/healthz")
def healthz():
    """Simple health check endpoint."""
    return {"status": "ok"}


def _check_db():
    """Try to open the DB and count tables, return status dict."""
    try:
        db_path = Path(current_app.config["DB_PATH"])
        if not db_path.exists():
            return {
                "ok": False,
                "message": f"DB file not found at {db_path}. "
                f"Run `python init_db.py` to create it.",
            }

        db = get_db()
        cur = db.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
        tables = [row["name"] for row in cur.fetchall()]
        return {
            "ok": True,
            "message": f"DB connected, {len(tables)} tables found.",
            "tables": tables,
        }
    except sqlite3.Error as e:
        return {"ok": False, "message": f"DB error: {e}"}
