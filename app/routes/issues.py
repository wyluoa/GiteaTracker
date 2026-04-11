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


# ── Side Panel (HTMX partial) ──

@bp.route("/issues/<int:issue_id>/cell/<int:node_id>")
@login_required
def side_panel(issue_id, node_id):
    """Return the side panel partial for a specific issue + node."""
    issue = issue_model.get_by_id(issue_id)
    if not issue:
        abort(404)
    node = node_model.get_by_id(node_id)
    if not node:
        abort(404)

    cell = state_model.get_state(issue_id, node_id)
    nodes = node_model.get_all_active()
    timeline = timeline_model.get_for_issue(issue_id)

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
               WHERE ug.user_id = ? AND gn.node_id = ? LIMIT 1""",
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
    """Update a cell's state/check_in_date/short_note and create timeline entry."""
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
    has_change = (
        new_state != old_state or
        new_check_in != old_check_in or
        new_note != old_note
    )

    if has_change:
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

        # Handle attachments
        from app.routes.attachments import save_attachments
        files = request.files.getlist("attachments")
        if files:
            save_attachments(entry_id, files)

        # Refresh issue cache
        issue_model.refresh_cache(issue_id)

    # Return updated side panel via HTMX, and trigger cell refresh on main table
    response = make_response(side_panel(issue_id, node_id))
    if has_change:
        import json
        response.headers["HX-Trigger"] = json.dumps({
            "cellUpdated": {"issueId": issue_id, "nodeId": node_id}
        })
    return response


# ── Cell partial (for updating the main table cell after edit) ──

@bp.route("/issues/<int:issue_id>/cell/<int:node_id>/chip")
@login_required
def cell_chip(issue_id, node_id):
    """Return just the cell chip partial for HTMX swap on main table."""
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
    """Add a general comment to the issue timeline."""
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
    """Add a meeting note to the issue timeline."""
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
    """Return filtered timeline partial."""
    issue = issue_model.get_by_id(issue_id)
    if not issue:
        abort(404)

    entry_type = request.args.get("type", "").strip() or None
    timeline = timeline_model.get_for_issue(issue_id, entry_type=entry_type)
    nodes = node_model.get_all_active()
    node_map = {n["id"]: n["display_name"] for n in nodes}

    return render_template(
        "partials/timeline.html",
        issue=issue,
        timeline=timeline,
        node_map=node_map,
        filter_type=entry_type,
    )


# ── Meeting Mode ──

@bp.route("/meeting/<int:year>/<int:week>")
@login_required
def meeting_mode(year, week):
    """Meeting mode page — list issues for a given week with textarea for each."""
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
@login_required
def meeting_mode_submit(year, week):
    """Submit meeting notes for multiple issues at once."""
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


# ── Close Issue ──

@bp.route("/issues/<int:issue_id>/close", methods=["POST"])
@login_required
def close_issue(issue_id):
    """Close an issue (set status=closed)."""
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


# ── Reopen Issue ──

@bp.route("/issues/<int:issue_id>/reopen", methods=["POST"])
@super_user_required
def reopen_issue(issue_id):
    """Reopen a closed issue (super user only)."""
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
@login_required
@can_edit_node("node_id")
def quick_done(issue_id, node_id):
    """Quick mark a cell as done (used from calendar view)."""
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
    """Batch update node state for multiple issues."""
    data = request.get_json() if request.is_json else None
    if not data:
        return jsonify({"error": "invalid request"}), 400

    issue_ids = data.get("issue_ids", [])
    node_id = data.get("node_id", type=int) if isinstance(data.get("node_id"), int) else None
    if data.get("node_id") and not node_id:
        try:
            node_id = int(data["node_id"])
        except (ValueError, TypeError):
            pass
    new_state = data.get("state", "").strip() or None
    note = data.get("note", "").strip() or None

    if not issue_ids or not node_id:
        return jsonify({"error": "缺少必要欄位"}), 400

    node = node_model.get_by_id(node_id)
    if not node:
        return jsonify({"error": "Node 不存在"}), 404

    # Check permission
    if not g.current_user["is_super_user"]:
        db = get_db()
        perm = db.execute(
            """SELECT 1 FROM user_groups ug
               JOIN group_nodes gn ON ug.group_id = gn.group_id
               WHERE ug.user_id = ? AND gn.node_id = ? LIMIT 1""",
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
