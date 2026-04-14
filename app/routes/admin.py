"""
Admin routes — super user only backend.
"""
import json
import os
import uuid
from datetime import datetime, timezone

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, g, current_app
)
from app.db import get_db
from app.routes.auth import super_user_required
from app.models import setting as setting_model
from app.models import node as node_model

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _audit(action, target_type=None, target_id=None, details=None):
    """Write an audit log entry."""
    db = get_db()
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
    """管理後台首頁
    ---
    tags:
      - Admin - Users
    responses:
      200:
        description: 顯示待審核人數、使用者數、群組數、Node 數
    """
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
    """待審核使用者列表
    ---
    tags:
      - Admin - Users
    responses:
      200:
        description: 列出所有 status=pending 的使用者
    """
    db = get_db()
    users = db.execute("SELECT * FROM users WHERE status = 'pending' ORDER BY created_at").fetchall()
    groups = db.execute("SELECT * FROM groups ORDER BY name").fetchall()
    return render_template("admin/pending_users.html", users=users, groups=groups)


@bp.route("/pending_users/<int:user_id>/approve", methods=["POST"])
@super_user_required
def approve_user(user_id):
    """核准使用者
    ---
    tags:
      - Admin - Users
    parameters:
      - name: user_id
        in: path
        type: integer
        required: true
      - name: group_ids
        in: formData
        type: array
        items:
          type: integer
        description: 指派的群組 ID 列表
    responses:
      302:
        description: 核准成功後重導至待審核列表
    """
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
    """拒絕使用者
    ---
    tags:
      - Admin - Users
    parameters:
      - name: user_id
        in: path
        type: integer
        required: true
    responses:
      302:
        description: 拒絕後重導至待審核列表
    """
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
    """使用者管理列表
    ---
    tags:
      - Admin - Users
    responses:
      200:
        description: 列出所有使用者及其群組
    """
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
    """更新使用者資料
    ---
    tags:
      - Admin - Users
    parameters:
      - name: user_id
        in: path
        type: integer
        required: true
      - name: display_name
        in: formData
        type: string
      - name: status
        in: formData
        type: string
        description: 狀態 (active/disabled)
      - name: is_super_user
        in: formData
        type: string
        description: 是否為管理員 ("1" 為是)
      - name: group_ids
        in: formData
        type: array
        items:
          type: integer
        description: 群組 ID 列表
    responses:
      302:
        description: 更新成功後重導至使用者列表
    """
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
    """群組管理列表
    ---
    tags:
      - Admin - Groups
    responses:
      200:
        description: 列出所有群組、成員、及關聯 Node
    """
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
    """建立新群組
    ---
    tags:
      - Admin - Groups
    parameters:
      - name: name
        in: formData
        type: string
        required: true
        description: 群組名稱
      - name: description
        in: formData
        type: string
        description: 群組描述
    responses:
      302:
        description: 建立成功後重導至群組列表
    """
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
    """更新群組 — 名稱、成員、關聯 Node
    ---
    tags:
      - Admin - Groups
    parameters:
      - name: group_id
        in: path
        type: integer
        required: true
      - name: name
        in: formData
        type: string
      - name: description
        in: formData
        type: string
      - name: member_ids
        in: formData
        type: array
        items:
          type: integer
        description: 成員 User ID 列表
      - name: node_ids
        in: formData
        type: array
        items:
          type: integer
        description: 關聯 Node ID 列表
    responses:
      302:
        description: 更新成功後重導至群組列表
    """
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
    """刪除群組
    ---
    tags:
      - Admin - Groups
    parameters:
      - name: group_id
        in: path
        type: integer
        required: true
    responses:
      302:
        description: 刪除成功後重導至群組列表
    """
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
    """Node 管理列表
    ---
    tags:
      - Admin - Nodes
    responses:
      200:
        description: 列出所有 Node (含停用的)
    """
    db = get_db()
    all_nodes = db.execute("SELECT * FROM nodes ORDER BY sort_order").fetchall()
    return render_template("admin/nodes.html", nodes=all_nodes)


@bp.route("/nodes/create", methods=["POST"])
@super_user_required
def create_node():
    """建立新 Node
    ---
    tags:
      - Admin - Nodes
    parameters:
      - name: code
        in: formData
        type: string
        required: true
        description: Node 代碼 (如 n_a10)
      - name: display_name
        in: formData
        type: string
        required: true
        description: 顯示名稱 (如 A10)
      - name: sort_order
        in: formData
        type: integer
        description: 排序 (預設 100)
    responses:
      302:
        description: 建立成功後重導至 Node 列表
    """
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
    """更新 Node
    ---
    tags:
      - Admin - Nodes
    parameters:
      - name: node_id
        in: path
        type: integer
        required: true
      - name: display_name
        in: formData
        type: string
      - name: sort_order
        in: formData
        type: integer
      - name: is_active
        in: formData
        type: string
        description: 是否啟用 ("1" 為啟用)
    responses:
      302:
        description: 更新成功後重導至 Node 列表
    """
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
    """紅線設定頁面
    ---
    tags:
      - Admin - Settings
    responses:
      200:
        description: 顯示目前的紅線年份/週次設定
    """
    red_year, red_week = setting_model.get_red_line()
    return render_template("admin/red_line.html", red_year=red_year, red_week=red_week)


@bp.route("/red_line", methods=["POST"])
@super_user_required
def update_red_line():
    """更新紅線
    ---
    tags:
      - Admin - Settings
    parameters:
      - name: week_year
        in: formData
        type: integer
        required: true
        description: 年份
      - name: week_number
        in: formData
        type: integer
        required: true
        description: 週次 (1-53)
    responses:
      302:
        description: 更新成功後重導至紅線設定頁
    """
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
    """SMTP 設定頁面
    ---
    tags:
      - Admin - Settings
    responses:
      200:
        description: 顯示目前的 SMTP 設定
    """
    keys = ["smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from_email"]
    settings = {k: setting_model.get(k, "") for k in keys}
    return render_template("admin/smtp.html", settings=settings)


@bp.route("/smtp", methods=["POST"])
@super_user_required
def update_smtp():
    """更新 SMTP 設定
    ---
    tags:
      - Admin - Settings
    parameters:
      - name: smtp_host
        in: formData
        type: string
      - name: smtp_port
        in: formData
        type: string
      - name: smtp_user
        in: formData
        type: string
      - name: smtp_password
        in: formData
        type: string
      - name: smtp_from_email
        in: formData
        type: string
    responses:
      302:
        description: 儲存成功後重導至 SMTP 設定頁
    """
    for key in ["smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from_email"]:
        val = request.form.get(key, "").strip()
        if val:
            setting_model.set(key, val)
    flash("SMTP 設定已儲存", "success")
    return redirect(url_for("admin.smtp"))


@bp.route("/smtp/test", methods=["POST"])
@super_user_required
def test_smtp():
    """測試 SMTP 寄信 (尚未實作)
    ---
    tags:
      - Admin - Settings
    responses:
      302:
        description: 重導至 SMTP 設定頁
    """
    # TODO: implement actual SMTP test email sending
    flash("SMTP 測試信功能將在後續實作", "warning")
    return redirect(url_for("admin.smtp"))


# ── Audit Log ──

@bp.route("/audit")
@super_user_required
def audit_log():
    """稽核日誌 — 分頁 + 依 action 篩選
    ---
    tags:
      - Admin - Audit
    parameters:
      - name: page
        in: query
        type: integer
        description: 頁碼 (預設 1)
      - name: action
        in: query
        type: string
        description: 篩選 action 類型
    responses:
      200:
        description: 列出稽核日誌，每頁 50 筆
    """
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


# ── Excel Update ──

EXCEL_TMP_DIR = "data/tmp"


def _ensure_tmp_dir():
    os.makedirs(EXCEL_TMP_DIR, exist_ok=True)


def _build_diff(excel_issues, db):
    """Compare parsed Excel issues against DB, return structured diff.

    Returns:
        {
            "new": [  # issues not in DB
                {"display_number": "108", "topic": "...", ...}
            ],
            "updated": [  # issues with at least one changed field
                {
                    "display_number": "42",
                    "issue_id": 5,
                    "topic": "...",
                    "fields": [
                        {"key": "topic", "label": "Topic",
                         "old": "Fix login", "new": "Fix SSO", "conflict": True},
                        ...
                    ],
                    "node_changes": [
                        {"node_id": 1, "node_name": "A10", "sub": "state",
                         "old": "developing", "new": "uat", "conflict": False},
                        ...
                    ]
                }
            ],
            "unchanged": 15  # count of issues with no diff
        }
    """
    from app.excel import STATE_LABELS

    # Pre-load all nodes for display names
    all_nodes = db.execute("SELECT id, display_name FROM nodes").fetchall()
    node_names = {n["id"]: n["display_name"] for n in all_nodes}

    new_issues = []
    updated_issues = []
    unchanged_count = 0

    issue_fields = [
        ("topic", "Topic"),
        ("requestor_name", "Owner"),
        ("jira_ticket", "JIRA"),
        ("icv", "ICV"),
        ("uat_path", "UAT Path"),
        ("status", "Status"),
        ("week_year", "Week Year"),
        ("week_number", "Week Number"),
    ]

    for ei in excel_issues:
        existing = db.execute(
            "SELECT * FROM issues WHERE display_number = ? AND is_deleted = 0",
            (ei["display_number"],),
        ).fetchone()

        if not existing:
            new_issues.append(ei)
            continue

        issue_id = existing["id"]
        fields = []
        for key, label in issue_fields:
            old_val = existing[key]
            new_val = ei.get(key)
            # Normalize for comparison
            old_str = str(old_val) if old_val is not None else ""
            new_str = str(new_val) if new_val is not None else ""
            if old_str != new_str:
                fields.append({
                    "key": key,
                    "label": label,
                    "old": old_str or "(empty)",
                    "new": new_str or "(empty)",
                    "conflict": bool(old_str and new_str and old_str != new_str),
                })

        # Compare node states
        node_changes = []
        db_states = db.execute(
            "SELECT * FROM issue_node_states WHERE issue_id = ?",
            (issue_id,),
        ).fetchall()
        db_state_map = {s["node_id"]: s for s in db_states}

        for node_id, excel_node in ei["nodes"].items():
            db_node = db_state_map.get(node_id)
            for sub, sub_label in [("state", "State"), ("check_in_date", "Check-in"), ("short_note", "Note")]:
                new_val = excel_node.get(sub)
                old_val = db_node[sub] if db_node else None
                old_str = str(old_val) if old_val is not None else ""
                new_str = str(new_val) if new_val is not None else ""
                if old_str != new_str:
                    display_new = new_str
                    display_old = old_str
                    if sub == "state":
                        display_new = STATE_LABELS.get(new_str, new_str) if new_str else ""
                        display_old = STATE_LABELS.get(old_str, old_str) if old_str else ""
                    node_changes.append({
                        "node_id": node_id,
                        "node_name": node_names.get(node_id, f"Node {node_id}"),
                        "sub": sub,
                        "sub_label": sub_label,
                        "old": display_old or "(empty)",
                        "new": display_new or "(empty)",
                        "raw_old": old_str,
                        "raw_new": new_str,
                        "conflict": bool(old_str and new_str and old_str != new_str),
                    })

        if fields or node_changes:
            updated_issues.append({
                "display_number": ei["display_number"],
                "issue_id": issue_id,
                "topic": existing["topic"],
                "fields": fields,
                "node_changes": node_changes,
            })
        else:
            unchanged_count += 1

    return {
        "new": new_issues,
        "updated": updated_issues,
        "unchanged": unchanged_count,
    }


@bp.route("/excel_update")
@super_user_required
def excel_update():
    """Excel 匯入頁面
    ---
    tags:
      - Admin - Excel
    responses:
      200:
        description: 顯示 Excel 上傳表單
    """
    return render_template("admin/excel_update.html")


@bp.route("/excel_update/preview", methods=["POST"])
@super_user_required
def excel_update_preview():
    """Excel 預覽 — 上傳 .xlsx 檔案，比對差異
    ---
    tags:
      - Admin - Excel
    consumes:
      - multipart/form-data
    parameters:
      - name: file
        in: formData
        type: file
        required: true
        description: .xlsx 檔案
    responses:
      200:
        description: 顯示 Excel 與 DB 的差異預覽 (新增/更新/無變更)
      302:
        description: 上傳失敗或無差異時重導至 Excel 匯入頁
    """
    file = request.files.get("file")
    if not file or not file.filename.endswith((".xlsx", ".xls")):
        flash("Please upload an .xlsx file", "error")
        return redirect(url_for("admin.excel_update"))

    _ensure_tmp_dir()
    batch_id = uuid.uuid4().hex
    xlsx_path = os.path.join(EXCEL_TMP_DIR, f"{batch_id}.xlsx")
    file.save(xlsx_path)

    try:
        from app.excel import parse_workbook

        nodes = node_model.get_all_active()
        node_lookup = {n["code"]: n["id"] for n in nodes}

        excel_issues = parse_workbook(xlsx_path, node_lookup)
        if not excel_issues:
            flash("No issues found in the uploaded Excel file", "error")
            os.remove(xlsx_path)
            return redirect(url_for("admin.excel_update"))

        db = get_db()
        diff = _build_diff(excel_issues, db)

        if not diff["new"] and not diff["updated"]:
            flash(f"No changes detected. All {diff['unchanged']} issues are up-to-date.", "info")
            os.remove(xlsx_path)
            return redirect(url_for("admin.excel_update"))

        # Save diff + parsed data to JSON for the apply step
        json_path = os.path.join(EXCEL_TMP_DIR, f"{batch_id}.json")
        # Convert node_id keys (int) to str for JSON
        serializable_issues = []
        for ei in excel_issues:
            ei_copy = dict(ei)
            ei_copy["nodes"] = {str(k): v for k, v in ei["nodes"].items()}
            serializable_issues.append(ei_copy)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"issues": serializable_issues, "diff": diff}, f,
                       ensure_ascii=False)

        return render_template("admin/excel_preview.html",
                               diff=diff, batch_id=batch_id,
                               filename=file.filename)
    except Exception as e:
        os.remove(xlsx_path)
        flash(f"Error parsing Excel: {e}", "error")
        return redirect(url_for("admin.excel_update"))


@bp.route("/excel_update/apply", methods=["POST"])
@super_user_required
def excel_update_apply():
    """Excel 套用 — 將預覽中勾選的變更寫入 DB
    ---
    tags:
      - Admin - Excel
    parameters:
      - name: batch_id
        in: formData
        type: string
        required: true
        description: 預覽步驟產生的 batch ID
      - name: new_issue
        in: formData
        type: array
        items:
          type: string
        description: 勾選要新增的 issue display_number 列表
      - name: update_field
        in: formData
        type: array
        items:
          type: string
        description: 勾選要更新的欄位 (格式 "display_number:field_key")
      - name: update_node
        in: formData
        type: array
        items:
          type: string
        description: 勾選要更新的 Node (格式 "display_number:node_id:sub")
    responses:
      302:
        description: 套用完成後重導至 Excel 匯入頁
    """
    batch_id = request.form.get("batch_id", "")
    if not batch_id or not batch_id.isalnum():
        flash("Invalid batch ID", "error")
        return redirect(url_for("admin.excel_update"))

    json_path = os.path.join(EXCEL_TMP_DIR, f"{batch_id}.json")
    xlsx_path = os.path.join(EXCEL_TMP_DIR, f"{batch_id}.xlsx")

    if not os.path.exists(json_path):
        flash("Preview data expired. Please upload the file again.", "error")
        return redirect(url_for("admin.excel_update"))

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    excel_issues = data["issues"]
    # Restore int keys for nodes
    for ei in excel_issues:
        ei["nodes"] = {int(k): v for k, v in ei["nodes"].items()}

    # Collect selected items from form checkboxes
    selected_new = set(request.form.getlist("new_issue"))
    selected_updates = set(request.form.getlist("update_field"))
    selected_nodes = set(request.form.getlist("update_node"))

    db = get_db()
    now_str = _now()
    user_id = g.current_user["id"]
    user_name = g.current_user["display_name"]

    created_count = 0
    updated_count = 0

    # Build lookup: display_number -> excel issue
    excel_map = {ei["display_number"]: ei for ei in excel_issues}

    # Apply new issues
    for ei in excel_issues:
        dn = ei["display_number"]
        if dn not in selected_new:
            continue

        existing = db.execute(
            "SELECT id FROM issues WHERE display_number = ?", (dn,)
        ).fetchone()
        if existing:
            continue  # safety: skip if somehow already exists

        cur = db.execute(
            """INSERT INTO issues
               (display_number, topic, requestor_name, owner_user_id,
                week_year, week_number, jira_ticket, icv, uat_path,
                status, created_at, updated_at, latest_update_at,
                created_by_user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (dn, ei["topic"], ei["requestor_name"], None,
             ei["week_year"], ei["week_number"], ei["jira_ticket"],
             ei["icv"], ei["uat_path"], ei["status"],
             now_str, now_str, now_str, user_id),
        )
        issue_id = cur.lastrowid

        # Insert all node states for new issue
        for node_id, ns in ei["nodes"].items():
            db.execute(
                """INSERT INTO issue_node_states
                   (issue_id, node_id, state, check_in_date, short_note,
                    updated_at, updated_by_user_id, updated_by_name_snapshot)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (issue_id, node_id, ns["state"], ns["check_in_date"],
                 ns["short_note"], now_str, user_id, user_name),
            )

        # Timeline entry
        db.execute(
            """INSERT INTO timeline_entries
               (issue_id, entry_type, body, author_user_id,
                author_name_snapshot, created_at)
               VALUES (?, 'comment', ?, ?, ?, ?)""",
            (issue_id, "Created via Excel upload", user_id, user_name, now_str),
        )
        created_count += 1

    # Apply field updates for existing issues
    # Parse selected_updates: format "42:topic"
    updates_by_issue = {}  # display_number -> list of field keys
    for key in selected_updates:
        parts = key.split(":", 1)
        if len(parts) == 2:
            updates_by_issue.setdefault(parts[0], []).append(parts[1])

    # Parse selected_nodes: format "42:node_id:sub"
    node_updates_by_issue = {}  # display_number -> list of (node_id, sub)
    for key in selected_nodes:
        parts = key.split(":", 2)
        if len(parts) == 3:
            node_updates_by_issue.setdefault(parts[0], []).append(
                (int(parts[1]), parts[2]))

    all_dns = set(updates_by_issue.keys()) | set(node_updates_by_issue.keys())
    for dn in all_dns:
        ei = excel_map.get(dn)
        if not ei:
            continue

        existing = db.execute(
            "SELECT * FROM issues WHERE display_number = ? AND is_deleted = 0",
            (dn,),
        ).fetchone()
        if not existing:
            continue

        issue_id = existing["id"]
        change_details = []

        # Apply issue field changes
        for field_key in updates_by_issue.get(dn, []):
            new_val = ei.get(field_key)
            old_val = existing[field_key]
            if str(new_val or "") != str(old_val or ""):
                db.execute(
                    f"UPDATE issues SET {field_key}=?, updated_at=? WHERE id=?",
                    (new_val, now_str, issue_id),
                )
                change_details.append(f"{field_key}: {old_val} -> {new_val}")

        # Apply node state changes
        for node_id, sub in node_updates_by_issue.get(dn, []):
            new_val = ei["nodes"].get(node_id, {}).get(sub)

            db_state = db.execute(
                "SELECT * FROM issue_node_states WHERE issue_id = ? AND node_id = ?",
                (issue_id, node_id),
            ).fetchone()

            old_val = db_state[sub] if db_state else None

            if db_state:
                db.execute(
                    f"""UPDATE issue_node_states SET {sub}=?, updated_at=?,
                        updated_by_user_id=?, updated_by_name_snapshot=?
                        WHERE issue_id=? AND node_id=?""",
                    (new_val, now_str, user_id, user_name, issue_id, node_id),
                )
            else:
                node_data = ei["nodes"].get(node_id, {})
                db.execute(
                    """INSERT INTO issue_node_states
                       (issue_id, node_id, state, check_in_date, short_note,
                        updated_at, updated_by_user_id, updated_by_name_snapshot)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (issue_id, node_id, node_data.get("state"),
                     node_data.get("check_in_date"), node_data.get("short_note"),
                     now_str, user_id, user_name),
                )

            # Timeline entry for node state changes
            if sub == "state":
                node_row = db.execute(
                    "SELECT display_name FROM nodes WHERE id = ?", (node_id,)
                ).fetchone()
                node_name = node_row["display_name"] if node_row else f"Node {node_id}"
                db.execute(
                    """INSERT INTO timeline_entries
                       (issue_id, entry_type, node_id, old_state, new_state,
                        body, author_user_id, author_name_snapshot, created_at)
                       VALUES (?, 'state_change', ?, ?, ?, ?, ?, ?, ?)""",
                    (issue_id, node_id, old_val, new_val,
                     f"Updated via Excel upload ({node_name})",
                     user_id, user_name, now_str),
                )

            change_details.append(f"node {node_id}.{sub}: {old_val} -> {new_val}")

        if change_details:
            # Update issue cache
            cache = db.execute(
                """SELECT
                     MAX(updated_at) as latest,
                     MIN(CASE WHEN state IN ('done', 'unneeded') THEN 1
                              WHEN state IS NULL THEN 0
                              ELSE 0 END) as all_done
                   FROM issue_node_states WHERE issue_id = ?""",
                (issue_id,),
            ).fetchone()
            db.execute(
                "UPDATE issues SET latest_update_at=?, all_nodes_done=?, updated_at=? WHERE id=?",
                (cache["latest"], cache["all_done"] or 0, now_str, issue_id),
            )
            updated_count += 1

    db.commit()

    _audit("excel_update", "issues", None, {
        "filename": request.form.get("filename", ""),
        "created": created_count,
        "updated": updated_count,
    })

    # Clean up temp files
    for path in (json_path, xlsx_path):
        if os.path.exists(path):
            os.remove(path)

    flash(f"Excel update completed: {created_count} new, {updated_count} updated", "success")
    return redirect(url_for("admin.excel_update"))
