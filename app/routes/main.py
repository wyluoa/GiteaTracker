"""
Main routes — tracker view and health check.
"""
from flask import Blueprint, render_template, g

from app.routes.auth import login_required
from app.models import issue as issue_model
from app.models import node as node_model
from app.models import issue_node_state as state_model
from app.models import setting as setting_model

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def tracker():
    """Main tracker view — read-only for Phase 1."""
    nodes = node_model.get_all_active()
    ongoing_issues = issue_model.get_ongoing()
    on_hold_issues = issue_model.get_on_hold()

    # Bulk load all node states
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

    return render_template(
        "tracker.html",
        nodes=nodes,
        week_groups=week_groups,
        on_hold_issues=on_hold_issues,
        all_states=all_states,
        red_line_year=red_line_year,
        red_line_week=red_line_week,
        user=g.current_user,
    )


@bp.route("/healthz")
def healthz():
    """Simple health check endpoint."""
    return {"status": "ok"}
