"""Node model — CRUD + active filtering."""
from app.db import get_db


def create_node(code, display_name, sort_order, is_active=True):
    db = get_db()
    cur = db.execute(
        "INSERT INTO nodes (code, display_name, sort_order, is_active) VALUES (?, ?, ?, ?)",
        (code, display_name, sort_order, int(is_active)),
    )
    db.commit()
    return cur.lastrowid


def get_all_active():
    return get_db().execute(
        "SELECT * FROM nodes WHERE is_active = 1 ORDER BY sort_order"
    ).fetchall()


def get_by_id(node_id):
    return get_db().execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()


def get_by_code(code):
    return get_db().execute("SELECT * FROM nodes WHERE code = ?", (code,)).fetchone()
