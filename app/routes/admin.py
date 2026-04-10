"""
Admin routes — super user only backend.
"""
from datetime import datetime, timezone

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, g
)
from app.db import get_db
from app.routes.auth import super_user_required
from app.models import setting as setting_model

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _audit(action, target_type=None, target_id=None, details=None):
    """Write an audit log entry."""
    db = get_db()
    import json
    db.execute(
        """INSERT INTO audit_log (actor_user_id, action, target_type, target_id, details, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (g.current_user["id"], action, target_type, target_id,
         json.dumps(details, ensure_ascii=False) if details else None, _now()),
    )
    db.commit()


# ── Admin index ──

@bp.route("/")
@super_user_required
def index():
    db = get_db()
    pending_count = db.execute("SELECT COUNT(*) as c FROM users WHERE status = 'pending'").fetchone()["c"]
    user_count = db.execute("SELECT COUNT(*) as c FROM users WHERE status != 'disabled'").fetchone()["c"]
    group_count = db.execute("SELECT COUNT(*) as c FROM groups").fetchone()["c"]
    node_count = db.execute("SELECT COUNT(*) as c FROM nodes WHERE is_active = 1").fetchone()["c"]
    return render_template("admin/index.html",
                           pending_count=pending_count, user_count=user_count,
                           group_count=group_count, node_count=node_count)


# ── Pending Users ──

@bp.route("/pending_users")
@super_user_required
def pending_users():
    db = get_db()
    users = db.execute("SELECT * FROM users WHERE status = 'pending' ORDER BY created_at").fetchall()
    groups = db.execute("SELECT * FROM groups ORDER BY name").fetchall()
    return render_template("admin/pending_users.html", users=users, groups=groups)


@bp.route("/pending_users/<int:user_id>/approve", methods=["POST"])
@super_user_required
def approve_user(user_id):
    db = get_db()
    group_ids = request.form.getlist("group_ids", type=int)

    db.execute("UPDATE users SET status = 'active', updated_at = ? WHERE id = ?",
               (_now(), user_id))
    for gid in group_ids:
        db.execute("INSERT OR IGNORE INTO user_groups (user_id, group_id) VALUES (?, ?)",
                   (user_id, gid))
    db.commit()
    _audit("approve_user", "user", user_id, {"groups": group_ids})
    flash("帳號已核准", "success")
    return redirect(url_for("admin.pending_users"))


@bp.route("/pending_users/<int:user_id>/reject", methods=["POST"])
@super_user_required
def reject_user(user_id):
    db = get_db()
    db.execute("UPDATE users SET status = 'disabled', updated_at = ? WHERE id = ?",
               (_now(), user_id))
    db.commit()
    _audit("disable_user", "user", user_id, {"reason": "registration rejected"})
    flash("帳號已拒絕", "success")
    return redirect(url_for("admin.pending_users"))


# ── Users ──

@bp.route("/users")
@super_user_required
def users():
    db = get_db()
    all_users = db.execute(
        "SELECT * FROM users WHERE username != 'legacy' ORDER BY created_at"
    ).fetchall()
    groups = db.execute("SELECT * FROM groups ORDER BY name").fetchall()

    # Build user -> groups mapping
    user_groups = {}
    rows = db.execute(
        """SELECT ug.user_id, g.id as group_id, g.name
           FROM user_groups ug JOIN groups g ON ug.group_id = g.id"""
    ).fetchall()
    for r in rows:
        user_groups.setdefault(r["user_id"], []).append({"id": r["group_id"], "name": r["name"]})

    return render_template("admin/users.html", users=all_users, groups=groups,
                           user_groups=user_groups)


@bp.route("/users/<int:user_id>/update", methods=["POST"])
@super_user_required
def update_user(user_id):
    db = get_db()
    display_name = request.form.get("display_name", "").strip()
    status = request.form.get("status", "active")
    is_super = request.form.get("is_super_user") == "1"
    group_ids = request.form.getlist("group_ids", type=int)

    if display_name:
        db.execute(
            "UPDATE users SET display_name=?, status=?, is_super_user=?, updated_at=? WHERE id=?",
            (display_name, status, int(is_super), _now(), user_id),
        )

    # Rebuild user groups
    db.execute("DELETE FROM user_groups WHERE user_id = ?", (user_id,))
    for gid in group_ids:
        db.execute("INSERT INTO user_groups (user_id, group_id) VALUES (?, ?)",
                   (user_id, gid))
    db.commit()
    _audit("update_user", "user", user_id,
           {"display_name": display_name, "status": status, "is_super_user": is_super, "groups": group_ids})
    flash("使用者已更新", "success")
    return redirect(url_for("admin.users"))


# ── Groups ──

@bp.route("/groups")
@super_user_required
def groups():
    db = get_db()
    all_groups = db.execute("SELECT * FROM groups ORDER BY name").fetchall()
    all_users = db.execute("SELECT * FROM users WHERE status = 'active' ORDER BY display_name").fetchall()
    all_nodes = db.execute("SELECT * FROM nodes WHERE is_active = 1 ORDER BY sort_order").fetchall()

    # Build group -> members/nodes mappings
    group_members = {}
    for r in db.execute("SELECT * FROM user_groups").fetchall():
        group_members.setdefault(r["group_id"], []).append(r["user_id"])
    group_nodes = {}
    for r in db.execute("SELECT * FROM group_nodes").fetchall():
        group_nodes.setdefault(r["group_id"], []).append(r["node_id"])

    return render_template("admin/groups.html",
                           groups=all_groups, users=all_users, nodes=all_nodes,
                           group_members=group_members, group_nodes=group_nodes)


@bp.route("/groups/create", methods=["POST"])
@super_user_required
def create_group():
    db = get_db()
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip() or None
    if not name:
        flash("Group 名稱不能為空", "error")
        return redirect(url_for("admin.groups"))

    cur = db.execute("INSERT INTO groups (name, description, created_at) VALUES (?, ?, ?)",
                     (name, description, _now()))
    db.commit()
    _audit("create_group", "group", cur.lastrowid, {"name": name})
    flash(f"Group '{name}' 已建立", "success")
    return redirect(url_for("admin.groups"))


@bp.route("/groups/<int:group_id>/update", methods=["POST"])
@super_user_required
def update_group(group_id):
    db = get_db()
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip() or None
    member_ids = request.form.getlist("member_ids", type=int)
    node_ids = request.form.getlist("node_ids", type=int)

    if name:
        db.execute("UPDATE groups SET name=?, description=? WHERE id=?",
                   (name, description, group_id))

    db.execute("DELETE FROM user_groups WHERE group_id = ?", (group_id,))
    for uid in member_ids:
        db.execute("INSERT INTO user_groups (user_id, group_id) VALUES (?, ?)", (uid, group_id))

    db.execute("DELETE FROM group_nodes WHERE group_id = ?", (group_id,))
    for nid in node_ids:
        db.execute("INSERT INTO group_nodes (group_id, node_id) VALUES (?, ?)", (group_id, nid))

    db.commit()
    _audit("update_group", "group", group_id,
           {"name": name, "members": member_ids, "nodes": node_ids})
    flash("Group 已更新", "success")
    return redirect(url_for("admin.groups"))


@bp.route("/groups/<int:group_id>/delete", methods=["POST"])
@super_user_required
def delete_group(group_id):
    db = get_db()
    group = db.execute("SELECT name FROM groups WHERE id = ?", (group_id,)).fetchone()
    db.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    db.commit()
    _audit("delete_group", "group", group_id, {"name": group["name"] if group else None})
    flash("Group 已刪除", "success")
    return redirect(url_for("admin.groups"))


# ── Nodes ──

@bp.route("/nodes")
@super_user_required
def nodes():
    db = get_db()
    all_nodes = db.execute("SELECT * FROM nodes ORDER BY sort_order").fetchall()
    return render_template("admin/nodes.html", nodes=all_nodes)


@bp.route("/nodes/create", methods=["POST"])
@super_user_required
def create_node():
    db = get_db()
    code = request.form.get("code", "").strip()
    display_name = request.form.get("display_name", "").strip()
    sort_order = request.form.get("sort_order", type=int, default=100)

    if not code or not display_name:
        flash("Code 和顯示名稱都不能為空", "error")
        return redirect(url_for("admin.nodes"))

    db.execute("INSERT INTO nodes (code, display_name, sort_order, is_active) VALUES (?, ?, ?, 1)",
               (code, display_name, sort_order))
    db.commit()
    _audit("create_node", "node", None, {"code": code, "display_name": display_name})
    flash(f"Node '{display_name}' 已建立", "success")
    return redirect(url_for("admin.nodes"))


@bp.route("/nodes/<int:node_id>/update", methods=["POST"])
@super_user_required
def update_node(node_id):
    db = get_db()
    display_name = request.form.get("display_name", "").strip()
    sort_order = request.form.get("sort_order", type=int)
    is_active = request.form.get("is_active") == "1"

    if display_name and sort_order is not None:
        db.execute("UPDATE nodes SET display_name=?, sort_order=?, is_active=? WHERE id=?",
                   (display_name, sort_order, int(is_active), node_id))
        db.commit()
        _audit("update_node", "node", node_id,
               {"display_name": display_name, "sort_order": sort_order, "is_active": is_active})
    flash("Node 已更新", "success")
    return redirect(url_for("admin.nodes"))


# ── Red Line ──

@bp.route("/red_line")
@super_user_required
def red_line():
    red_year, red_week = setting_model.get_red_line()
    return render_template("admin/red_line.html", red_year=red_year, red_week=red_week)


@bp.route("/red_line", methods=["POST"])
@super_user_required
def update_red_line():
    year = request.form.get("week_year", type=int)
    week = request.form.get("week_number", type=int)

    if year and week and 1 <= week <= 53:
        old_year, old_week = setting_model.get_red_line()
        setting_model.set("red_line_week_year", str(year))
        setting_model.set("red_line_week_number", str(week))
        _audit("set_red_line", "setting", None,
               {"old": f"wk{old_year}{old_week:02d}" if old_year else "none",
                "new": f"wk{year}{week:02d}"})
        flash(f"紅線已設定為 wk{year}{week:02d}", "success")
    else:
        flash("請輸入有效的年份和週次 (1-53)", "error")

    return redirect(url_for("admin.red_line"))


# ── SMTP Settings ──

@bp.route("/smtp")
@super_user_required
def smtp():
    keys = ["smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from_email"]
    settings = {k: setting_model.get(k, "") for k in keys}
    return render_template("admin/smtp.html", settings=settings)


@bp.route("/smtp", methods=["POST"])
@super_user_required
def update_smtp():
    for key in ["smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from_email"]:
        val = request.form.get(key, "").strip()
        if val:
            setting_model.set(key, val)
    flash("SMTP 設定已儲存", "success")
    return redirect(url_for("admin.smtp"))


@bp.route("/smtp/test", methods=["POST"])
@super_user_required
def test_smtp():
    # TODO: implement actual SMTP test email sending
    flash("SMTP 測試信功能將在後續實作", "warning")
    return redirect(url_for("admin.smtp"))


# ── Audit Log ──

@bp.route("/audit")
@super_user_required
def audit_log():
    db = get_db()
    page = request.args.get("page", 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page

    action_filter = request.args.get("action", "").strip()

    if action_filter:
        logs = db.execute(
            """SELECT al.*, u.display_name as actor_name
               FROM audit_log al LEFT JOIN users u ON al.actor_user_id = u.id
               WHERE al.action = ?
               ORDER BY al.created_at DESC LIMIT ? OFFSET ?""",
            (action_filter, per_page, offset),
        ).fetchall()
    else:
        logs = db.execute(
            """SELECT al.*, u.display_name as actor_name
               FROM audit_log al LEFT JOIN users u ON al.actor_user_id = u.id
               ORDER BY al.created_at DESC LIMIT ? OFFSET ?""",
            (per_page, offset),
        ).fetchall()

    actions = db.execute("SELECT DISTINCT action FROM audit_log ORDER BY action").fetchall()
    return render_template("admin/audit_log.html",
                           logs=logs, actions=actions, action_filter=action_filter,
                           page=page)
