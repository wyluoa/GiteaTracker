"""Issue model — CRUD + filtering + cache updates."""
from datetime import datetime, timezone

from app.db import get_db


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_issue(*, display_number, topic, owner_user_id=None,
                 requestor_user_id=None, requestor_name=None,
                 week_year, week_number, jira_ticket=None, icv=None,
                 uat_path=None, gitea_issue_url=None, status="ongoing",
                 created_by_user_id=None):
    db = get_db()
    now = _now()
    cur = db.execute(
        """INSERT INTO issues
           (display_number, topic, requestor_user_id, requestor_name,
            owner_user_id, week_year, week_number, jira_ticket, icv,
            uat_path, gitea_issue_url, status,
            created_at, created_by_user_id, updated_at, latest_update_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (display_number, topic, requestor_user_id, requestor_name,
         owner_user_id, week_year, week_number, jira_ticket, icv,
         uat_path, gitea_issue_url, status,
         now, created_by_user_id, now, now),
    )
    db.commit()
    return cur.lastrowid


def get_by_display_number(display_number):
    return get_db().execute(
        "SELECT * FROM issues WHERE display_number = ? AND is_deleted = 0",
        (display_number,),
    ).fetchone()


def get_by_id(issue_id):
    return get_db().execute(
        "SELECT * FROM issues WHERE id = ? AND is_deleted = 0",
        (issue_id,),
    ).fetchone()


def get_ongoing():
    """Return ongoing issues ordered by week (old first) then display_number."""
    return get_db().execute(
        """SELECT * FROM issues
           WHERE status = 'ongoing' AND is_deleted = 0
           ORDER BY week_year, week_number, CAST(display_number AS INTEGER)"""
    ).fetchall()


def get_on_hold():
    return get_db().execute(
        """SELECT * FROM issues
           WHERE status = 'on_hold' AND is_deleted = 0
           ORDER BY week_year, week_number, CAST(display_number AS INTEGER)"""
    ).fetchall()


def get_closed(limit=50, offset=0):
    return get_db().execute(
        """SELECT * FROM issues
           WHERE status = 'closed' AND is_deleted = 0
           ORDER BY closed_at DESC
           LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()


def count_closed():
    row = get_db().execute(
        "SELECT COUNT(*) as cnt FROM issues WHERE status = 'closed' AND is_deleted = 0"
    ).fetchone()
    return row["cnt"]


def count_by_status(status):
    row = get_db().execute(
        "SELECT COUNT(*) as cnt FROM issues WHERE status = ? AND is_deleted = 0",
        (status,),
    ).fetchone()
    return row["cnt"]


def count_ready_to_close():
    row = get_db().execute(
        "SELECT COUNT(*) as cnt FROM issues WHERE status = 'ongoing' AND all_nodes_done = 1 AND is_deleted = 0"
    ).fetchone()
    return row["cnt"]


def dashboard_node_counts(red_line_year, red_line_week):
    """Per-node count of ongoing issues above red line that are NOT done/unneeded."""
    if not red_line_year or not red_line_week:
        return {}
    db = get_db()
    rows = db.execute(
        """SELECT s.node_id, COUNT(DISTINCT i.id) as cnt
           FROM issues i
           JOIN issue_node_states s ON i.id = s.issue_id
           WHERE i.status = 'ongoing' AND i.is_deleted = 0
             AND (s.state IS NULL OR s.state NOT IN ('done', 'unneeded'))
             AND (i.week_year < ? OR (i.week_year = ? AND i.week_number <= ?))
           GROUP BY s.node_id""",
        (red_line_year, red_line_year, red_line_week),
    ).fetchall()
    return {r["node_id"]: r["cnt"] for r in rows}


def update_issue(issue_id, **fields):
    """Update arbitrary fields on an issue."""
    if not fields:
        return
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [issue_id]
    db = get_db()
    db.execute(f"UPDATE issues SET {set_clause} WHERE id = ?", vals)
    db.commit()


def refresh_cache(issue_id):
    """Recalculate and update the cache columns for an issue."""
    db = get_db()
    row = db.execute(
        """SELECT
             MAX(updated_at) as latest,
             MIN(CASE WHEN state IN ('done', 'unneeded') THEN 1
                      WHEN state IS NULL THEN 0
                      ELSE 0 END) as all_done
           FROM issue_node_states
           WHERE issue_id = ?""",
        (issue_id,),
    ).fetchone()

    if row:
        db.execute(
            "UPDATE issues SET latest_update_at = ?, all_nodes_done = ?, updated_at = ? WHERE id = ?",
            (row["latest"], row["all_done"] or 0, _now(), issue_id),
        )
        db.commit()


def get_dashboard_trends():
    """Return weekly cumulative data for dashboard charts.

    Each issue is classified into a phase:
      - Close:  status = 'closed'
      - UAT:    any node in ('uat', 'uat_done')
      - Dev:    any node in 'developing'
      - TBD:    everything else (ongoing, nodes blank or tbd)

    Returns dict with keys: weeks, cumulative, closing_rates.
    """
    db = get_db()

    issues = db.execute(
        """SELECT id, week_year, week_number, status
           FROM issues WHERE is_deleted = 0
           ORDER BY week_year, week_number"""
    ).fetchall()

    if not issues:
        return {"weeks": [], "cumulative": [], "closing_rates": []}

    # Determine dominant non-done phase per issue
    issue_ids = [i["id"] for i in issues]
    ph = ",".join("?" * len(issue_ids))
    state_rows = db.execute(
        f"""SELECT issue_id,
                   MAX(CASE WHEN state IN ('uat', 'uat_done') THEN 3
                            WHEN state = 'developing' THEN 2
                            WHEN state = 'tbd' THEN 1
                            ELSE 0 END) as max_phase
            FROM issue_node_states
            WHERE issue_id IN ({ph})
            GROUP BY issue_id""",
        issue_ids,
    ).fetchall()
    phase_map = {r["issue_id"]: r["max_phase"] for r in state_rows}

    def _phase(issue):
        if issue["status"] == "closed":
            return "Close"
        mp = phase_map.get(issue["id"], 0)
        if mp >= 3:
            return "UAT"
        if mp >= 2:
            return "Dev"
        return "TBD"

    # Collect unique weeks and count per phase
    weeks_set = sorted({(i["week_year"], i["week_number"]) for i in issues})
    week_counts = {}
    for i in issues:
        wk = (i["week_year"], i["week_number"])
        week_counts.setdefault(wk, {"TBD": 0, "Dev": 0, "UAT": 0, "Close": 0})
        week_counts[wk][_phase(i)] += 1

    # Build cumulative series
    cum = {"TBD": 0, "Dev": 0, "UAT": 0, "Close": 0}
    result_weeks = []
    result_cum = []
    result_rates = []

    for wk in weeks_set:
        c = week_counts.get(wk, {"TBD": 0, "Dev": 0, "UAT": 0, "Close": 0})
        for p in ("TBD", "Dev", "UAT", "Close"):
            cum[p] += c[p]
        total = sum(cum.values())
        rate = round(cum["Close"] / total * 100, 1) if total else 0
        result_weeks.append(f"wk{wk[0]}{wk[1]:02d}")
        result_cum.append(dict(cum))
        result_rates.append(rate)

    return {
        "weeks": result_weeks,
        "cumulative": result_cum,
        "closing_rates": result_rates,
    }
