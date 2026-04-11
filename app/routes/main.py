"""
Main routes — tracker view, search/filter, mark read, export.
"""
from datetime import date, datetime, timezone
from io import BytesIO

from flask import Blueprint, render_template, request, redirect, url_for, flash, g, send_file

from app.db import get_db
from app.routes.auth import login_required
from app.models import issue as issue_model
from app.models import node as node_model
from app.models import issue_node_state as state_model
from app.models import setting as setting_model
from app.models import user as user_model

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def tracker():
    """Main tracker view with search/filter support."""
    nodes = node_model.get_all_active()

    # ── Search & filter params ──
    q = request.args.get("q", "").strip()
    filter_owner = request.args.get("owner", "").strip()
    filter_state = request.args.get("state", "").strip()
    filter_week_from = request.args.get("week_from", "").strip()
    filter_week_to = request.args.get("week_to", "").strip()

    # ── Advanced filter: up to 3 node+state pairs ──
    adv_filters = []
    for i in range(1, 4):
        anode = request.args.get(f"adv_node_{i}", "").strip()
        astate = request.args.get(f"adv_state_{i}", "").strip()
        if anode or astate:
            adv_filters.append({"node": anode, "state": astate, "index": i})

    ongoing_issues = issue_model.get_ongoing()
    on_hold_issues = issue_model.get_on_hold()

    has_basic_filter = q or filter_owner or filter_state or filter_week_from or filter_week_to

    # Apply basic filters (text, owner, week range)
    if has_basic_filter:
        ongoing_issues = _apply_filters(ongoing_issues, nodes, q, filter_owner, filter_state,
                                         filter_week_from, filter_week_to)
        on_hold_issues = _apply_filters(on_hold_issues, nodes, q, filter_owner, filter_state,
                                         filter_week_from, filter_week_to)

    # Bulk load all node states
    all_issue_ids = [i["id"] for i in ongoing_issues] + [i["id"] for i in on_hold_issues]
    all_states = state_model.get_all_states_for_issues(all_issue_ids)

    # For basic state filter (no specific node): any node matches
    if filter_state and all_states:
        filtered_ids = set()
        for issue_id, node_states in all_states.items():
            for nid, cell in node_states.items():
                if filter_state == "__blank__":
                    if not cell["state"]:
                        filtered_ids.add(issue_id)
                        break
                elif cell["state"] == filter_state:
                    filtered_ids.add(issue_id)
                    break
        ongoing_issues = [i for i in ongoing_issues if i["id"] in filtered_ids]
        on_hold_issues = [i for i in on_hold_issues if i["id"] in filtered_ids]
        all_issue_ids = [i["id"] for i in ongoing_issues] + [i["id"] for i in on_hold_issues]
        all_states = state_model.get_all_states_for_issues(all_issue_ids)

    # Apply advanced node+state filters (AND logic)
    if adv_filters:
        all_current_ids = set(i["id"] for i in ongoing_issues) | set(i["id"] for i in on_hold_issues)
        for af in adv_filters:
            af_node_id = int(af["node"]) if af["node"] else None
            af_state = af["state"]
            filtered_ids = set()
            for issue_id in all_current_ids:
                node_states = all_states.get(issue_id, {})
                if af_node_id and af_state:
                    cell = node_states.get(af_node_id)
                    if af_state == "__blank__":
                        if not cell or not cell["state"]:
                            filtered_ids.add(issue_id)
                    elif cell and cell["state"] == af_state:
                        filtered_ids.add(issue_id)
                elif af_node_id and not af_state:
                    cell = node_states.get(af_node_id)
                    if cell and cell["state"]:
                        filtered_ids.add(issue_id)
                elif not af_node_id and af_state:
                    for nid, cell in node_states.items():
                        if af_state == "__blank__":
                            if not cell["state"]:
                                filtered_ids.add(issue_id)
                                break
                        elif cell["state"] == af_state:
                            filtered_ids.add(issue_id)
                            break
            ongoing_issues = [i for i in ongoing_issues if i["id"] in filtered_ids]
            on_hold_issues = [i for i in on_hold_issues if i["id"] in filtered_ids]
            all_issue_ids = [i["id"] for i in ongoing_issues] + [i["id"] for i in on_hold_issues]
            all_states = state_model.get_all_states_for_issues(all_issue_ids)

    # Group ongoing issues by week
    week_groups = []
    current_key = None
    current_group = None
    for issue in ongoing_issues:
        key = (issue["week_year"], issue["week_number"])
        if key != current_key:
            current_key = key
            current_group = {"week_year": key[0], "week_number": key[1], "issues": []}
            week_groups.append(current_group)
        current_group["issues"].append(issue)

    # Red line
    red_line_year, red_line_week = setting_model.get_red_line()

    # Current ISO week
    today = date.today()
    iso = today.isocalendar()

    # Version diff: last_viewed_at
    last_viewed = g.current_user["last_viewed_at"]

    # Distinct owners for filter dropdown
    db = get_db()
    owners = db.execute(
        "SELECT DISTINCT requestor_name FROM issues WHERE requestor_name IS NOT NULL AND is_deleted = 0 ORDER BY requestor_name"
    ).fetchall()

    return render_template(
        "tracker.html",
        nodes=nodes,
        week_groups=week_groups,
        on_hold_issues=on_hold_issues,
        all_states=all_states,
        red_line_year=red_line_year,
        red_line_week=red_line_week,
        current_week_year=iso[0],
        current_week_number=iso[1],
        last_viewed=last_viewed,
        user=g.current_user,
        # Filter state
        q=q, filter_owner=filter_owner, filter_state=filter_state,
        filter_week_from=filter_week_from, filter_week_to=filter_week_to,
        owners=[r["requestor_name"] for r in owners],
        adv_filters=adv_filters,
    )


def _apply_filters(issues, nodes, q, owner, state, week_from, week_to):
    result = issues
    if q:
        ql = q.lower()
        result = [i for i in result if
                  ql in (i["display_number"] or "").lower() or
                  ql in (i["topic"] or "").lower() or
                  ql in (i["jira_ticket"] or "").lower() or
                  ql in (i["uat_path"] or "").lower()]
    if owner:
        result = [i for i in result if i["requestor_name"] == owner]
    if week_from:
        try:
            wy, wn = int(week_from[:4]), int(week_from[4:])
            result = [i for i in result if (i["week_year"], i["week_number"]) >= (wy, wn)]
        except (ValueError, IndexError):
            pass
    if week_to:
        try:
            wy, wn = int(week_to[:4]), int(week_to[4:])
            result = [i for i in result if (i["week_year"], i["week_number"]) <= (wy, wn)]
        except (ValueError, IndexError):
            pass
    return result


# ── Mark all as read ──

@bp.route("/mark_all_read", methods=["POST"])
@login_required
def mark_all_read():
    user_model.update_last_viewed(g.current_user["id"])
    flash("已標記全部為已讀", "success")
    return redirect(url_for("main.tracker"))


# ── Export Excel ──

@bp.route("/export")
@login_required
def export_excel():
    import openpyxl
    from openpyxl.styles import PatternFill, Font, Alignment

    nodes = node_model.get_all_active()
    ongoing = issue_model.get_ongoing()
    on_hold = issue_model.get_on_hold()
    all_issues = list(ongoing) + list(on_hold)
    all_ids = [i["id"] for i in all_issues]
    all_states = state_model.get_all_states_for_issues(all_ids)

    STATE_LABELS = {
        "done": "Done", "uat_done": "UAT done", "uat": "UAT",
        "developing": "Developing", "tbd": "TBD", "unneeded": "Unneeded",
    }

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ongoing"

    # Header
    headers = ["#", "Status", "Owner"] + [n["display_name"] for n in nodes] + ["JIRA", "UAT Path", "Topic"]
    ws.append(headers)
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font

    current_week = None
    for issue in all_issues:
        wk = (issue["week_year"], issue["week_number"])
        if wk != current_week:
            current_week = wk
            ws.append([f"wk{wk[0]}{wk[1]:02d}"])

        row_data = [issue["display_number"], issue["status"], issue["requestor_name"] or ""]
        states = all_states.get(issue["id"], {})
        for node in nodes:
            cell = states.get(node["id"])
            if cell and cell["state"]:
                label = STATE_LABELS.get(cell["state"], cell["state"])
                if cell["check_in_date"]:
                    label += f"\n{cell['check_in_date']}"
                row_data.append(label)
            else:
                row_data.append("")
        row_data.extend([issue["jira_ticket"] or "", issue["uat_path"] or "", issue["topic"]])
        ws.append(row_data)

    # Auto-width
    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 40)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"gitea_tracker_{date.today().isoformat()}.xlsx"
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name=filename)


@bp.route("/healthz")
def healthz():
    return {"status": "ok"}
