"""
Issue routes — side panel, cell editing, timeline, meeting mode, close/reopen, batch ops.
"""
import json
from datetime import datetime, timezone

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, g, abort, make_response, jsonify
)
from app.db import get_db
from app.routes.auth import login_required, can_edit_node, super_user_required
from app.models import issue as issue_model
from app.models import node as node_model
from app.models import issue_node_state as state_model
from app.models import timeline as timeline_model
from app.models import setting as setting_model

bp = Blueprint("issues", __name__)


def _now():
    return datetime.now(timezone.utc).isoformat()


# ── Role-gated state transitions ──
# Done: super_user only. Unneeded: super_user or manager. Others: any editor.

def _state_change_allowed(user, new_state):
    """Returns (allowed: bool, error_msg: str|None) for setting a cell to new_state."""
    if new_state == "done" and not user["is_super_user"]:
        return False, "只有管理員 (super user) 能將狀態改為 Done"
    if new_state == "unneeded" and not (user["is_super_user"] or user["is_manager"]):
        return False, "將狀態改為 Unneeded 需要管理員或 Manager 權限"
    return True, None


# ── Side Panel (HTMX partial) ──

@bp.route("/issues/<int:issue_id>/cell/<int:node_id>")
@login_required
def side_panel(issue_id, node_id):
    """Side Panel — 取得特定 Issue + Node 的側邊面板 (HTMX partial)
    ---
    tags:
      - Issues
    parameters:
      - name: issue_id
        in: path
        type: integer
        required: true
      - name: node_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: 渲染 side_panel.html partial (含 cell 狀態、timeline)
      404:
        description: Issue 或 Node 不存在
    """
    issue = issue_model.get_by_id(issue_id)
    if not issue:
        abort(404)
    node = node_model.get_by_id(node_id)
    if not node:
        abort(404)

    cell = state_model.get_state(issue_id, node_id)
    nodes = node_model.get_all_active()
    timeline = timeline_model.get_for_issue(issue_id, node_id=node_id)

    # Get node display names for timeline rendering
    node_map = {n["id"]: n["display_name"] for n in nodes}

    # Check edit permission
    can_edit = False
    if g.current_user["is_super_user"]:
        can_edit = True
    else:
        from app.db import get_db
        db = get_db()
        perm = db.execute(
            """SELECT 1 FROM user_groups ug
               JOIN group_nodes gn ON ug.group_id = gn.group_id
               JOIN groups gr ON ug.group_id = gr.id
               WHERE ug.user_id = ? AND gn.node_id = ? AND gr.is_active = 1 LIMIT 1""",
            (g.current_user["id"], node_id),
        ).fetchone()
        can_edit = perm is not None

    return render_template(
        "partials/side_panel.html",
        issue=issue,
        node=node,
        cell=cell,
        nodes=nodes,
        node_map=node_map,
        timeline=timeline,
        user=g.current_user,
        can_edit=can_edit,
    )


# ── Cell Update ──

@bp.route("/issues/<int:issue_id>/cell/<int:node_id>", methods=["POST"])
@login_required
@can_edit_node("node_id")
def update_cell(issue_id, node_id):
    """更新 Cell — 修改狀態/check-in 日期/備註，產生 timeline 紀錄
    ---
    tags:
      - Issues
    parameters:
      - name: issue_id
        in: path
        type: integer
        required: true
      - name: node_id
        in: path
        type: integer
        required: true
      - name: state
        in: formData
        type: string
        description: 新狀態 (done/uat_done/uat/developing/tbd/unneeded)
      - name: check_in_date
        in: formData
        type: string
        description: Check-in 日期 (YYYY-MM-DD)
      - name: short_note
        in: formData
        type: string
        description: 簡短備註
      - name: body
        in: formData
        type: string
        description: 更新說明 (寫入 timeline)
      - name: attachments
        in: formData
        type: file
        description: 附件 (PNG/JPG/PDF，最多 3 個)
    responses:
      200:
        description: 回傳更新後的 side_panel partial，並透過 HX-Trigger 通知前端刷新 cell
      404:
        description: Issue 或 Node 不存在
    """
    issue = issue_model.get_by_id(issue_id)
    if not issue:
        abort(404)
    node = node_model.get_by_id(node_id)
    if not node:
        abort(404)

    # Read current state
    old_cell = state_model.get_state(issue_id, node_id)
    old_state = old_cell["state"] if old_cell else None
    old_check_in = old_cell["check_in_date"] if old_cell else None
    old_note = old_cell["short_note"] if old_cell else None

    # Read form values
    new_state = request.form.get("state", "").strip() or None
    new_check_in = request.form.get("check_in_date", "").strip() or None
    new_note = request.form.get("short_note", "").strip() or None
    update_body = request.form.get("body", "").strip() or None

    # Detect changes
    state_changed = new_state != old_state
    cell_changed = (
        state_changed or
        new_check_in != old_check_in or
        new_note != old_note
    )
    files = [f for f in request.files.getlist("attachments") if f and f.filename]
    note_only = (not cell_changed) and (bool(update_body) or bool(files))

    # Role gate: restrict who can transition to Done / Unneeded
    if state_changed:
        allowed, reason = _state_change_allowed(g.current_user, new_state)
        if not allowed:
            flash(reason, "error")
            return side_panel(issue_id, node_id)
        # Mandatory note whenever the state actually changes
        if not update_body:
            flash("狀態變動必須填寫「更新說明」", "error")
            return side_panel(issue_id, node_id)

    entry_id = None
    if cell_changed:
        # Update the cell
        state_model.upsert_state(
            issue_id, node_id,
            state=new_state,
            check_in_date=new_check_in,
            short_note=new_note,
            updated_by_user_id=g.current_user["id"],
            updated_by_name_snapshot=g.current_user["display_name"],
        )

        # Create state_change timeline entry
        entry_id = timeline_model.create_entry(
            issue_id=issue_id,
            entry_type="state_change",
            node_id=node_id,
            old_state=old_state,
            new_state=new_state,
            old_check_in_date=old_check_in,
            new_check_in_date=new_check_in,
            old_short_note=old_note,
            new_short_note=new_note,
            body=update_body,
            author_user_id=g.current_user["id"],
            author_name_snapshot=g.current_user["display_name"],
        )

        # Refresh issue cache
        issue_model.refresh_cache(issue_id)
    elif note_only:
        # No cell-field change, but user wrote a note or uploaded files:
        # keep them as a node-scoped comment so nothing is silently dropped.
        entry_id = timeline_model.create_entry(
            issue_id=issue_id,
            entry_type="comment",
            node_id=node_id,
            body=update_body,
            author_user_id=g.current_user["id"],
            author_name_snapshot=g.current_user["display_name"],
        )

    if entry_id and files:
        from app.routes.attachments import save_attachments
        save_attachments(entry_id, files)

    # Return updated side panel via HTMX, and trigger cell refresh on main table
    response = make_response(side_panel(issue_id, node_id))
    if cell_changed:
        response.headers["HX-Trigger"] = json.dumps({
            "cellUpdated": {"issueId": issue_id, "nodeId": node_id}
        })
    return response


# ── Cell partial (for updating the main table cell after edit) ──

@bp.route("/issues/<int:issue_id>/cell/<int:node_id>/chip")
@login_required
def cell_chip(issue_id, node_id):
    """Cell Chip — 取得單一 cell 的小元件 (用於 HTMX 更新主表格)
    ---
    tags:
      - Issues
    parameters:
      - name: issue_id
        in: path
        type: integer
        required: true
      - name: node_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: 渲染 cell_chip.html partial
    """
    issue = issue_model.get_by_id(issue_id)
    cell = state_model.get_state(issue_id, node_id)
    node = node_model.get_by_id(node_id)

    red_line_year, red_line_week = setting_model.get_red_line()
    above_red = False
    if red_line_year and red_line_week and issue:
        above_red = (
            issue["week_year"] < red_line_year or
            (issue["week_year"] == red_line_year and issue["week_number"] <= red_line_week)
        )

    return render_template(
        "partials/cell_chip.html",
        issue=issue,
        node=node,
        cell=cell,
        above_red=above_red,
    )


# ── Timeline: Add Comment ──

@bp.route("/issues/<int:issue_id>/timeline/comment", methods=["POST"])
@login_required
def add_comment(issue_id):
    """新增留言到 Timeline
    ---
    tags:
      - Issues
    parameters:
      - name: issue_id
        in: path
        type: integer
        required: true
      - name: body
        in: formData
        type: string
        required: true
        description: 留言內容
      - name: node_id
        in: formData
        type: integer
        description: 當前 Node ID (用於回傳 side panel)
      - name: attachments
        in: formData
        type: file
        description: 附件
    responses:
      200:
        description: 回傳更新後的 side_panel partial
      404:
        description: Issue 不存在
    """
    issue = issue_model.get_by_id(issue_id)
    if not issue:
        abort(404)

    body = request.form.get("body", "").strip()
    if not body:
        flash("留言內容不能為空", "error")
        # Return to the side panel of the first node
        nodes = node_model.get_all_active()
        node_id = int(request.form.get("node_id", nodes[0]["id"]))
        return side_panel(issue_id, node_id)

    node_id = int(request.form.get("node_id", 0))

    entry_id = timeline_model.create_entry(
        issue_id=issue_id,
        entry_type="comment",
        body=body,
        author_user_id=g.current_user["id"],
        author_name_snapshot=g.current_user["display_name"],
    )

    from app.routes.attachments import save_attachments
    files = request.files.getlist("attachments")
    if files:
        save_attachments(entry_id, files)

    return side_panel(issue_id, node_id)


# ── Timeline: Add Meeting Note ──

@bp.route("/issues/<int:issue_id>/timeline/meeting_note", methods=["POST"])
@login_required
def add_meeting_note(issue_id):
    """新增會議紀錄到 Timeline
    ---
    tags:
      - Issues
    parameters:
      - name: issue_id
        in: path
        type: integer
        required: true
      - name: body
        in: formData
        type: string
        required: true
        description: 會議紀錄內容
      - name: node_id
        in: formData
        type: integer
        description: 當前 Node ID
      - name: meeting_week_year
        in: formData
        type: integer
        description: 會議週年份
      - name: meeting_week_number
        in: formData
        type: integer
        description: 會議週次
      - name: attachments
        in: formData
        type: file
        description: 附件
    responses:
      200:
        description: 回傳更新後的 side_panel partial
      404:
        description: Issue 不存在
    """
    issue = issue_model.get_by_id(issue_id)
    if not issue:
        abort(404)

    body = request.form.get("body", "").strip()
    if not body:
        flash("會議紀錄內容不能為空", "error")
        nodes = node_model.get_all_active()
        node_id = int(request.form.get("node_id", nodes[0]["id"]))
        return side_panel(issue_id, node_id)

    node_id = int(request.form.get("node_id", 0))
    week_year = request.form.get("meeting_week_year", type=int)
    week_number = request.form.get("meeting_week_number", type=int)

    entry_id = timeline_model.create_entry(
        issue_id=issue_id,
        entry_type="meeting_note",
        body=body,
        meeting_week_year=week_year,
        meeting_week_number=week_number,
        author_user_id=g.current_user["id"],
        author_name_snapshot=g.current_user["display_name"],
    )

    from app.routes.attachments import save_attachments
    files = request.files.getlist("attachments")
    if files:
        save_attachments(entry_id, files)

    return side_panel(issue_id, node_id)


# ── Timeline: Filter (HTMX partial) ──

@bp.route("/issues/<int:issue_id>/timeline")
@login_required
def timeline_partial(issue_id):
    """Timeline 篩選 — 取得篩選後的 timeline partial
    ---
    tags:
      - Issues
    parameters:
      - name: issue_id
        in: path
        type: integer
        required: true
      - name: type
        in: query
        type: string
        description: 篩選類型 (state_change/comment/meeting_note)
    responses:
      200:
        description: 渲染 timeline.html partial
      404:
        description: Issue 不存在
    """
    issue = issue_model.get_by_id(issue_id)
    if not issue:
        abort(404)

    entry_type = request.args.get("type", "").strip() or None
    filter_node_id = request.args.get("node_id", type=int) or None
    timeline = timeline_model.get_for_issue(issue_id, entry_type=entry_type, node_id=filter_node_id)
    nodes = node_model.get_all_active()
    node_map = {n["id"]: n["display_name"] for n in nodes}

    return render_template(
        "partials/timeline.html",
        issue=issue,
        timeline=timeline,
        node_map=node_map,
        filter_type=entry_type,
        filter_node_id=filter_node_id,
    )


# ── Meeting Mode ──

@bp.route("/meeting/<int:year>/<int:week>")
@super_user_required
def meeting_mode(year, week):
    """會議模式 — 列出指定週的所有 issues，每題附文字框
    ---
    tags:
      - Meeting
    parameters:
      - name: year
        in: path
        type: integer
        required: true
        description: 年份
      - name: week
        in: path
        type: integer
        required: true
        description: 週次
    responses:
      200:
        description: 渲染 meeting_mode.html
    """
    from app.db import get_db
    db = get_db()

    issues = db.execute(
        """SELECT * FROM issues
           WHERE week_year = ? AND week_number = ?
             AND status IN ('ongoing', 'on_hold')
             AND is_deleted = 0
           ORDER BY CAST(display_number AS INTEGER)""",
        (year, week),
    ).fetchall()

    return render_template(
        "meeting_mode.html",
        year=year,
        week=week,
        issues=issues,
        user=g.current_user,
    )


@bp.route("/meeting/<int:year>/<int:week>", methods=["POST"])
@super_user_required
def meeting_mode_submit(year, week):
    """提交會議紀錄 — 批次儲存該週所有 issues 的會議紀錄
    ---
    tags:
      - Meeting
    parameters:
      - name: year
        in: path
        type: integer
        required: true
      - name: week
        in: path
        type: integer
        required: true
      - name: note_{issue_id}
        in: formData
        type: string
        description: 各 issue 的會議紀錄 (欄位名為 note_加上 issue ID)
    responses:
      302:
        description: 儲存成功後重導至 tracker
    """
    from app.db import get_db
    db = get_db()

    issues = db.execute(
        """SELECT * FROM issues
           WHERE week_year = ? AND week_number = ?
             AND status IN ('ongoing', 'on_hold')
             AND is_deleted = 0
           ORDER BY CAST(display_number AS INTEGER)""",
        (year, week),
    ).fetchall()

    count = 0
    for issue in issues:
        body = request.form.get(f"note_{issue['id']}", "").strip()
        if body:
            timeline_model.create_entry(
                issue_id=issue["id"],
                entry_type="meeting_note",
                body=body,
                meeting_week_year=year,
                meeting_week_number=week,
                author_user_id=g.current_user["id"],
                author_name_snapshot=g.current_user["display_name"],
            )
            count += 1

    flash(f"已儲存 {count} 筆會議紀錄", "success")
    return redirect(url_for("main.tracker"))


# ── Row Update (inline edit all nodes) ──

@bp.route("/issues/<int:issue_id>/row_update", methods=["POST"])
@super_user_required
def row_update(issue_id):
    """整行更新 — 一次修改一個 issue 的所有 Node 狀態
    ---
    tags:
      - Issues
    consumes:
      - application/json
    parameters:
      - name: issue_id
        in: path
        type: integer
        required: true
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            states:
              type: object
              description: 'Node ID → new state 的 mapping，如 {"1": "done", "2": "uat"}'
            comment:
              type: string
              description: 備註 (選填，寫入 timeline)
    responses:
      200:
        description: '回傳 {"ok": true, "updated": N}'
      404:
        description: Issue 不存在
    """
    issue = issue_model.get_by_id(issue_id)
    if not issue:
        return jsonify({"error": "Issue not found"}), 404

    data = request.get_json() if request.is_json else None
    if not data:
        return jsonify({"error": "invalid request"}), 400

    states_map = data.get("states", {})
    comment = (data.get("comment") or "").strip() or None
    if not states_map:
        return jsonify({"ok": True, "updated": 0})

    # Pre-flight: role gate for every target state before writing anything
    for node_id_str, tgt_state in states_map.items():
        tgt = tgt_state.strip() if tgt_state else None
        allowed, reason = _state_change_allowed(g.current_user, tgt)
        if not allowed:
            return jsonify({"error": reason}), 403

    # Determine whether any cell will actually change — if so, comment is required
    any_real_change = False
    for node_id_str, tgt_state in states_map.items():
        try:
            nid = int(node_id_str)
        except (ValueError, TypeError):
            continue
        old_cell = state_model.get_state(issue_id, nid)
        old_state = old_cell["state"] if old_cell else None
        tgt = tgt_state.strip() if tgt_state else None
        if tgt != old_state:
            any_real_change = True
            break
    if any_real_change and not comment:
        return jsonify({"error": "狀態變動必須填寫「更新說明」"}), 400

    updated = 0
    for node_id_str, new_state in states_map.items():
        node_id = int(node_id_str)
        node = node_model.get_by_id(node_id)
        if not node:
            continue

        # Permission check
        if not g.current_user["is_super_user"]:
            db = get_db()
            perm = db.execute(
                """SELECT 1 FROM user_groups ug
                   JOIN group_nodes gn ON ug.group_id = gn.group_id
                   WHERE ug.user_id = ? AND gn.node_id = ? LIMIT 1""",
                (g.current_user["id"], node_id),
            ).fetchone()
            if not perm:
                continue  # skip nodes user can't edit

        old_cell = state_model.get_state(issue_id, node_id)
        old_state = old_cell["state"] if old_cell else None
        new_state = new_state.strip() if new_state else None

        if new_state != old_state:
            state_model.upsert_state(
                issue_id, node_id,
                state=new_state,
                check_in_date=old_cell["check_in_date"] if old_cell else None,
                short_note=old_cell["short_note"] if old_cell else None,
                updated_by_user_id=g.current_user["id"],
                updated_by_name_snapshot=g.current_user["display_name"],
            )
            timeline_model.create_entry(
                issue_id=issue_id,
                entry_type="state_change",
                node_id=node_id,
                old_state=old_state,
                new_state=new_state,
                body=comment,
                author_user_id=g.current_user["id"],
                author_name_snapshot=g.current_user["display_name"],
            )
            updated += 1

    if updated:
        issue_model.refresh_cache(issue_id)

    return jsonify({"ok": True, "updated": updated})


# ── Close Issue ──

@bp.route("/issues/<int:issue_id>/close", methods=["POST"])
@login_required
def close_issue(issue_id):
    """關單 — 將 issue 狀態設為 closed
    ---
    tags:
      - Issues
    parameters:
      - name: issue_id
        in: path
        type: integer
        required: true
      - name: closed_note
        in: formData
        type: string
        description: 關單備註
    responses:
      302:
        description: 關單成功後重導至 tracker
      404:
        description: Issue 不存在
    """
    issue = issue_model.get_by_id(issue_id)
    if not issue:
        abort(404)

    closed_note = request.form.get("closed_note", "").strip() or None

    issue_model.update_issue(
        issue_id,
        status="closed",
        closed_at=_now(),
        closed_by_user_id=g.current_user["id"],
        closed_note=closed_note,
        pending_close=0,
    )

    timeline_model.create_entry(
        issue_id=issue_id,
        entry_type="comment",
        body=f"關單{(' — ' + closed_note) if closed_note else ''}",
        author_user_id=g.current_user["id"],
        author_name_snapshot=g.current_user["display_name"],
    )

    # Audit log
    db = get_db()
    db.execute(
        """INSERT INTO audit_log (actor_user_id, action, target_type, target_id, details, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (g.current_user["id"], "close_issue", "issue", issue_id,
         json.dumps({"closed_note": closed_note}, ensure_ascii=False), _now()),
    )
    db.commit()

    flash(f"#{issue['display_number']} 已關單", "success")
    return redirect(url_for("main.tracker"))


# ── Update Closed Note ──

@bp.route("/issues/<int:issue_id>/closed_note", methods=["POST"])
@login_required
def update_closed_note(issue_id):
    """更新關單備註（super_user only）
    ---
    tags:
      - Issues
    parameters:
      - name: issue_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: JSON ok
    """
    if not g.current_user["is_super_user"]:
        return jsonify({"error": "需要管理員權限"}), 403
    issue = issue_model.get_by_id(issue_id)
    if not issue:
        return jsonify({"error": "not found"}), 404
    new_note = request.json.get("closed_note", "").strip() if request.is_json else ""
    issue_model.update_issue(issue_id, closed_note=new_note or None)
    return jsonify({"ok": True, "closed_note": new_note})


# ── Reopen Issue ──

@bp.route("/issues/<int:issue_id>/reopen", methods=["POST"])
@super_user_required
def reopen_issue(issue_id):
    """重新開啟 — 將已關單的 issue 重新開啟 (需管理員)
    ---
    tags:
      - Issues
    parameters:
      - name: issue_id
        in: path
        type: integer
        required: true
      - name: reason
        in: formData
        type: string
        description: 重開原因
    responses:
      302:
        description: 重開成功後重導至 closed 頁面
      404:
        description: Issue 不存在
    """
    issue = issue_model.get_by_id(issue_id)
    if not issue:
        abort(404)

    reason = request.form.get("reason", "").strip() or None

    issue_model.update_issue(
        issue_id,
        status="ongoing",
        closed_at=None,
        closed_by_user_id=None,
        closed_note=None,
        pending_close=0,
    )

    timeline_model.create_entry(
        issue_id=issue_id,
        entry_type="comment",
        body=f"重新開啟{(' — ' + reason) if reason else ''}",
        author_user_id=g.current_user["id"],
        author_name_snapshot=g.current_user["display_name"],
    )

    # Audit log
    db = get_db()
    db.execute(
        """INSERT INTO audit_log (actor_user_id, action, target_type, target_id, details, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (g.current_user["id"], "reopen_issue", "issue", issue_id,
         json.dumps({"reason": reason}, ensure_ascii=False), _now()),
    )
    db.commit()

    flash(f"#{issue['display_number']} 已重新開啟", "success")
    return redirect(url_for("main.closed"))


# ── Quick Done (calendar) ──

@bp.route("/issues/<int:issue_id>/cell/<int:node_id>/quick_done", methods=["POST"])
@super_user_required
def quick_done(issue_id, node_id):
    """快速標記完成 — 從行事曆快速將 cell 設為 done
    ---
    tags:
      - Issues
    parameters:
      - name: issue_id
        in: path
        type: integer
        required: true
      - name: node_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: '回傳 JSON {"ok": true}'
        schema:
          type: object
          properties:
            ok:
              type: boolean
      404:
        description: Issue 或 Node 不存在
    """
    issue = issue_model.get_by_id(issue_id)
    if not issue:
        abort(404)
    node = node_model.get_by_id(node_id)
    if not node:
        abort(404)

    old_cell = state_model.get_state(issue_id, node_id)
    old_state = old_cell["state"] if old_cell else None

    if old_state != "done":
        state_model.upsert_state(
            issue_id, node_id,
            state="done",
            check_in_date=old_cell["check_in_date"] if old_cell else None,
            short_note=old_cell["short_note"] if old_cell else None,
            updated_by_user_id=g.current_user["id"],
            updated_by_name_snapshot=g.current_user["display_name"],
        )
        timeline_model.create_entry(
            issue_id=issue_id,
            entry_type="state_change",
            node_id=node_id,
            old_state=old_state,
            new_state="done",
            author_user_id=g.current_user["id"],
            author_name_snapshot=g.current_user["display_name"],
        )
        issue_model.refresh_cache(issue_id)

    return jsonify({"ok": True})


# ── Batch Update ──

@bp.route("/issues/batch_update", methods=["POST"])
@login_required
def batch_update():
    """批次更新 — 一次修改多個 issues 的同一 Node 狀態
    ---
    tags:
      - Issues
    consumes:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - issue_ids
            - node_id
          properties:
            issue_ids:
              type: array
              items:
                type: integer
              description: 要更新的 issue ID 列表
            node_id:
              type: integer
              description: 要更新的 Node ID
            state:
              type: string
              description: 新狀態 (done/uat_done/uat/developing/tbd/unneeded)
            note:
              type: string
              description: 更新備註
    responses:
      200:
        description: 回傳更新結果
        schema:
          type: object
          properties:
            ok:
              type: boolean
            updated:
              type: integer
              description: 實際更新筆數
      400:
        description: 缺少必要欄位或 JSON 格式錯誤
      403:
        description: 無權限編輯此 Node
      404:
        description: Node 不存在
    """
    data = request.get_json() if request.is_json else None
    if not data:
        return jsonify({"error": "invalid request"}), 400

    issue_ids = data.get("issue_ids", [])
    try:
        node_id = int(data["node_id"]) if data.get("node_id") else None
    except (ValueError, TypeError):
        node_id = None
    new_state = (data.get("state") or "").strip() or None
    note = (data.get("note") or "").strip() or None

    if not issue_ids or not node_id:
        return jsonify({"error": "缺少必要欄位"}), 400

    node = node_model.get_by_id(node_id)
    if not node:
        return jsonify({"error": "Node 不存在"}), 404

    # Role gate for target state
    allowed, reason = _state_change_allowed(g.current_user, new_state)
    if not allowed:
        return jsonify({"error": reason}), 403

    # Note required when state will actually change for at least one issue
    any_real_change = False
    for iid in issue_ids:
        oc = state_model.get_state(iid, node_id)
        if (oc["state"] if oc else None) != new_state:
            any_real_change = True
            break
    if any_real_change and not note:
        return jsonify({"error": "狀態變動必須填寫「更新說明」"}), 400

    # Check permission
    if not g.current_user["is_super_user"]:
        db = get_db()
        perm = db.execute(
            """SELECT 1 FROM user_groups ug
               JOIN group_nodes gn ON ug.group_id = gn.group_id
               JOIN groups gr ON ug.group_id = gr.id
               WHERE ug.user_id = ? AND gn.node_id = ? AND gr.is_active = 1 LIMIT 1""",
            (g.current_user["id"], node_id),
        ).fetchone()
        if not perm:
            return jsonify({"error": "無權限編輯此 Node"}), 403

    updated = 0
    for iid in issue_ids:
        issue = issue_model.get_by_id(iid)
        if not issue:
            continue

        old_cell = state_model.get_state(iid, node_id)
        old_state = old_cell["state"] if old_cell else None

        if new_state != old_state:
            state_model.upsert_state(
                iid, node_id,
                state=new_state,
                check_in_date=old_cell["check_in_date"] if old_cell else None,
                short_note=old_cell["short_note"] if old_cell else None,
                updated_by_user_id=g.current_user["id"],
                updated_by_name_snapshot=g.current_user["display_name"],
            )
            timeline_model.create_entry(
                issue_id=iid,
                entry_type="state_change",
                node_id=node_id,
                old_state=old_state,
                new_state=new_state,
                body=note,
                author_user_id=g.current_user["id"],
                author_name_snapshot=g.current_user["display_name"],
            )
            issue_model.refresh_cache(iid)
            updated += 1

    return jsonify({"ok": True, "updated": updated})


# ── Soft Delete Issue ──

@bp.route("/issues/<int:issue_id>/delete", methods=["POST"])
@super_user_required
def delete_issue(issue_id):
    """刪除 Issue — 軟刪除 (需管理員)
    ---
    tags:
      - Issues
    parameters:
      - name: issue_id
        in: path
        type: integer
        required: true
    responses:
      302:
        description: 刪除成功後重導至上一頁或 tracker
      404:
        description: Issue 不存在
    """
    issue = issue_model.get_by_id(issue_id)
    if not issue:
        abort(404)

    issue_model.update_issue(issue_id, is_deleted=1)

    # Audit log
    db = get_db()
    db.execute(
        """INSERT INTO audit_log (actor_user_id, action, target_type, target_id, details, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (g.current_user["id"], "delete_issue", "issue", issue_id,
         json.dumps({"display_number": issue["display_number"], "topic": issue["topic"]}, ensure_ascii=False),
         _now()),
    )
    db.commit()

    flash(f"#{issue['display_number']} 已刪除", "warning")
    return redirect(request.referrer or url_for("main.tracker"))
