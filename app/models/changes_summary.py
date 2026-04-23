"""Aggregate 'what changed since my last visit' for the /changes summary page.

Reads from timeline_entries (state_change + field_change), plus issues
(created_at / closed_at) to assemble a per-issue summary since `since`.

Classification rules (what counts as "important"):
  - red line hit:   issue is above the red line (week ≤ red_line_week)
  - regression:     state went from a "more advanced" slot to a "less advanced"
                    one (Done→anything, UAT done→UAT, UAT→Dev/TBD)
  - check-in delay: check_in_date moved later by ≥ 1 day
  - new issue:      issue was created after `since`
  - closed:         issue status flipped to closed after `since`
  - reopened:       issue status flipped back to ongoing from closed after `since`

Non-important (still shown in the "general" section):
  - normal state progression (Dev→UAT, UAT→UAT done, UAT done→Done)
  - short_note edits
  - topic / owner / jira / uat_path edits
"""
from app.db import get_db
from app.models import setting as setting_model


# Advancement rank for progression/regression detection.
# Higher = more advanced. "unneeded" is treated as terminal-equivalent to Done.
_STATE_RANK = {
    None: 0,
    "":  0,
    "tbd": 1,
    "developing": 2,
    "uat": 3,
    "uat_done": 4,
    "done": 5,
    "unneeded": 5,
}

_STATE_LABEL = {
    "done": "Done", "uat_done": "UAT done", "uat": "UAT",
    "developing": "Dev", "tbd": "TBD", "unneeded": "Unneeded",
    None: "—", "": "—",
}

_FIELD_LABEL = {
    "topic": "Topic",
    "requestor_name": "Owner",
    "jira_ticket": "JIRA",
    "uat_path": "UAT Path",
}


def _is_above_red_line(week_year, week_number, red_year, red_week):
    if not (red_year and red_week) or week_year is None or week_number is None:
        return False
    if week_year < red_year:
        return True
    if week_year == red_year and week_number <= red_week:
        return True
    return False


def _classify_state_change(old_state, new_state):
    """Returns one of: 'regression' | 'progression' | 'lateral' | 'noop'."""
    if old_state == new_state:
        return "noop"
    o = _STATE_RANK.get(old_state, 0)
    n = _STATE_RANK.get(new_state, 0)
    if n < o:
        return "regression"
    if n > o:
        return "progression"
    return "lateral"


def _date_diff_days(old_date, new_date):
    """Return signed day-diff (new - old) for ISO 'YYYY-MM-DD' strings, or None."""
    from datetime import date
    def _parse(s):
        if not s or not isinstance(s, str):
            return None
        s = s.strip()
        try:
            if len(s) == 10 and s[4] == '-' and s[7] == '-':
                return date.fromisoformat(s)
        except ValueError:
            return None
        return None
    a = _parse(old_date)
    b = _parse(new_date)
    if a and b:
        return (b - a).days
    return None


def count_important(*, since):
    """Quick count of "該關心的" events since `since`, for navbar bell badge.

    Counts ALL authors (including the current user's own operations). This
    keeps the badge consistent with /changes page, which defaults to showing
    everything. User-level "hide own" toggle lives on the /changes page
    itself; the badge is a simple "how many important things happened".

    Much cheaper than full build_summary — runs a handful of aggregate
    queries, no per-event classification / folding.
    """
    if not since:
        return 0
    db = get_db()
    red_year, red_week = setting_model.get_red_line()

    total = 0

    # New issues
    row = db.execute(
        "SELECT COUNT(*) AS c FROM issues WHERE is_deleted = 0 AND created_at > ?",
        (since,),
    ).fetchone()
    total += row["c"]

    # Closed
    row = db.execute(
        """SELECT COUNT(*) AS c FROM issues
           WHERE is_deleted = 0 AND status = 'closed'
             AND closed_at IS NOT NULL AND closed_at > ?""",
        (since,),
    ).fetchone()
    total += row["c"]

    # State-change entries. We classify in Python since SQLite doesn't
    # have a nice way to encode the rank table. This set stays small even
    # with a week of activity so the loop is cheap.
    rows = db.execute(
        """SELECT t.old_state, t.new_state, t.old_check_in_date, t.new_check_in_date,
                  i.week_year, i.week_number
           FROM timeline_entries t
           JOIN issues i ON i.id = t.issue_id
           WHERE t.created_at > ?
             AND t.entry_type = 'state_change'
             AND i.is_deleted = 0""",
        (since,),
    ).fetchall()
    for r in rows:
        above = _is_above_red_line(r["week_year"], r["week_number"], red_year, red_week)
        important = False
        if above and r["old_state"] != r["new_state"]:
            important = True
        if _classify_state_change(r["old_state"], r["new_state"]) == "regression":
            important = True
        delta = _date_diff_days(r["old_check_in_date"], r["new_check_in_date"])
        if delta is not None and delta >= 1:
            important = True
        if important:
            total += 1

    return total


def build_summary(*, current_user_id, since, include_own=False, filter_node_id=None):
    """Aggregate changes since `since` ISO timestamp.

    include_own=False means drop entries authored by current_user_id
    (the default — users rarely want to see their own work back).

    filter_node_id, when set, restricts to cell-level events on that node
    only. Field changes, new-issue rows and close rows are dropped because
    they are issue-level and do not belong to any specific node — showing
    them under a node filter would be misleading.

    Returns dict:
      {
        'since': since,
        'red_line': (year, week) or (None, None),
        'counts': {...},
        'issues': [
          {
            'issue_id', 'display_number', 'topic', 'status',
            'above_red', 'closed', 'is_new',
            'events': [ {event dicts} ],
            'max_severity': 'important' | 'normal',
          },
          ...
        ],
      }
    """
    db = get_db()
    red_year, red_week = setting_model.get_red_line()

    # ── Timeline entries since `since` (state_change + field_change) ──
    if since:
        params = [since]
        if filter_node_id:
            type_clause = "AND t.entry_type = 'state_change' AND t.node_id = ? "
            params.append(filter_node_id)
        else:
            type_clause = "AND t.entry_type IN ('state_change', 'field_change') "
        tl_rows = db.execute(
            f"""SELECT t.*, i.display_number, i.topic, i.status,
                      i.week_year, i.week_number, i.is_deleted,
                      n.display_name as node_name
               FROM timeline_entries t
               JOIN issues i ON i.id = t.issue_id
               LEFT JOIN nodes n ON n.id = t.node_id
               WHERE t.created_at > ?
                 {type_clause}
                 AND i.is_deleted = 0
               ORDER BY t.created_at""",
            params,
        ).fetchall()
    else:
        tl_rows = []

    # ── New issues / closed issues / reopened issues ──
    # Skip these entirely under a node filter — they aren't node-specific.
    new_issue_rows = []
    closed_rows = []
    if since and not filter_node_id:
        new_issue_rows = db.execute(
            """SELECT id, display_number, topic, status, week_year, week_number,
                      created_at, created_by_user_id,
                      requestor_name
               FROM issues
               WHERE is_deleted = 0 AND created_at > ?
               ORDER BY created_at""",
            (since,),
        ).fetchall()
        closed_rows = db.execute(
            """SELECT id, display_number, topic, status, week_year, week_number,
                      closed_at, closed_by_user_id, closed_note
               FROM issues
               WHERE is_deleted = 0 AND status = 'closed'
                 AND closed_at IS NOT NULL AND closed_at > ?
               ORDER BY closed_at""",
            (since,),
        ).fetchall()

    # Build per-issue bucket
    issues = {}  # issue_id → dict

    def _get_bucket(issue_id, *, base):
        if issue_id not in issues:
            issues[issue_id] = {
                "issue_id": issue_id,
                "display_number": base["display_number"],
                "topic": base["topic"],
                "status": base["status"],
                "above_red": _is_above_red_line(
                    base["week_year"], base["week_number"], red_year, red_week
                ),
                "week_year": base["week_year"],
                "week_number": base["week_number"],
                "events": [],
                "is_new": False,
                "is_closed": False,
                "is_reopened": False,
            }
        return issues[issue_id]

    # Pass 1 — timeline entries
    for r in tl_rows:
        if not include_own and r["author_user_id"] == current_user_id:
            continue
        bucket = _get_bucket(r["issue_id"], base=r)

        if r["entry_type"] == "state_change":
            old_s = r["old_state"]
            new_s = r["new_state"]
            cls = _classify_state_change(old_s, new_s)
            # Fold: one cell row per (node_id) — keep earliest old, latest new.
            node_id = r["node_id"]
            key = ("cell", node_id)
            existing = next(
                (ev for ev in bucket["events"] if ev.get("_key") == key), None
            )
            date_delta = _date_diff_days(r["old_check_in_date"], r["new_check_in_date"])
            if existing:
                existing["new_state"] = new_s
                existing["new_check_in_date"] = r["new_check_in_date"]
                existing["new_short_note"] = r["new_short_note"]
                existing["last_author"] = r["author_name_snapshot"]
                existing["last_at"] = r["created_at"]
                existing["fold_count"] += 1
                # Re-classify against the absolute old→latest new
                existing["progression"] = _classify_state_change(
                    existing["old_state"], new_s
                )
                # Refresh date delta against current endpoints
                existing["check_in_delta_days"] = _date_diff_days(
                    existing["old_check_in_date"], r["new_check_in_date"]
                )
            else:
                bucket["events"].append({
                    "_key": key,
                    "type": "cell",
                    "node_id": node_id,
                    "node_name": r["node_name"],
                    "old_state": old_s,
                    "new_state": new_s,
                    "old_check_in_date": r["old_check_in_date"],
                    "new_check_in_date": r["new_check_in_date"],
                    "old_short_note": r["old_short_note"],
                    "new_short_note": r["new_short_note"],
                    "progression": cls,
                    "check_in_delta_days": date_delta,
                    "first_author": r["author_name_snapshot"],
                    "last_author": r["author_name_snapshot"],
                    "first_at": r["created_at"],
                    "last_at": r["created_at"],
                    "body": r["body"],
                    "fold_count": 1,
                })

        elif r["entry_type"] == "field_change":
            bucket["events"].append({
                "_key": ("field", r["field_name"], r["id"]),
                "type": "field",
                "field_name": r["field_name"],
                "field_label": _FIELD_LABEL.get(r["field_name"], r["field_name"]),
                "old_value": r["old_field_value"],
                "new_value": r["new_field_value"],
                "first_author": r["author_name_snapshot"],
                "last_author": r["author_name_snapshot"],
                "first_at": r["created_at"],
                "last_at": r["created_at"],
                "fold_count": 1,
            })

    # Pass 2 — new issues
    for r in new_issue_rows:
        if not include_own and r["created_by_user_id"] == current_user_id:
            continue
        bucket = _get_bucket(r["id"], base=r)
        bucket["is_new"] = True
        bucket["events"].append({
            "_key": ("new_issue",),
            "type": "new_issue",
            "created_at": r["created_at"],
            "requestor_name": r["requestor_name"],
            "first_at": r["created_at"],
            "last_at": r["created_at"],
            "fold_count": 1,
        })

    # Pass 3 — closed issues
    for r in closed_rows:
        if not include_own and r["closed_by_user_id"] == current_user_id:
            continue
        bucket = _get_bucket(r["id"], base=r)
        bucket["is_closed"] = True
        bucket["events"].append({
            "_key": ("closed",),
            "type": "closed",
            "closed_at": r["closed_at"],
            "closed_note": r["closed_note"],
            "first_at": r["closed_at"],
            "last_at": r["closed_at"],
            "fold_count": 1,
        })

    # ── Severity classification ──
    important_issue_ids = set()
    counts = {
        "red_line_events": 0,
        "regression_events": 0,
        "check_in_delay_events": 0,
        "new_issues": 0,
        "closed_issues": 0,
        "normal_events": 0,
        "total_events": 0,
        "total_issues": 0,
    }

    for iid, b in issues.items():
        max_sev = "normal"
        for ev in b["events"]:
            counts["total_events"] += 1
            is_important = False
            if ev["type"] == "cell":
                if b["above_red"] and (ev["old_state"] != ev["new_state"]):
                    ev["flag_red_line"] = True
                    counts["red_line_events"] += 1
                    is_important = True
                else:
                    ev["flag_red_line"] = False
                if ev.get("progression") == "regression":
                    ev["flag_regression"] = True
                    counts["regression_events"] += 1
                    is_important = True
                else:
                    ev["flag_regression"] = False
                delta = ev.get("check_in_delta_days")
                if delta is not None and delta >= 1:
                    ev["flag_delay"] = True
                    counts["check_in_delay_events"] += 1
                    is_important = True
                else:
                    ev["flag_delay"] = False
                if not is_important:
                    counts["normal_events"] += 1
            elif ev["type"] == "new_issue":
                counts["new_issues"] += 1
                is_important = True
            elif ev["type"] == "closed":
                counts["closed_issues"] += 1
                is_important = True
            elif ev["type"] == "field":
                counts["normal_events"] += 1
            ev["important"] = is_important
            if is_important:
                max_sev = "important"
        b["max_severity"] = max_sev
        if max_sev == "important":
            important_issue_ids.add(iid)
        # Clean internal fold keys (not needed in template)
        for ev in b["events"]:
            ev.pop("_key", None)

    counts["total_issues"] = len(issues)
    counts["important_issues"] = len(important_issue_ids)

    # Sort: important first (stable), newest activity first within each bucket.
    def _latest(b):
        return max((ev["last_at"] for ev in b["events"]), default="")

    issue_list = sorted(issues.values(), key=_latest, reverse=True)
    issue_list.sort(key=lambda b: 0 if b["max_severity"] == "important" else 1)

    return {
        "since": since,
        "red_line": (red_year, red_week),
        "counts": counts,
        "issues": issue_list,
        "state_label": _STATE_LABEL,
    }
