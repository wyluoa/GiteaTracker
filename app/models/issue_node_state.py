"""IssueNodeState model — per-issue per-node state cell."""
from datetime import datetime, timezone

from app.db import get_db


def _now():
    return datetime.now(timezone.utc).isoformat()


def get_states_for_issue(issue_id):
    """Return all node states for an issue, keyed by node_id."""
    rows = get_db().execute(
        "SELECT * FROM issue_node_states WHERE issue_id = ? ORDER BY node_id",
        (issue_id,),
    ).fetchall()
    return {row["node_id"]: row for row in rows}


def get_state(issue_id, node_id):
    return get_db().execute(
        "SELECT * FROM issue_node_states WHERE issue_id = ? AND node_id = ?",
        (issue_id, node_id),
    ).fetchone()


def upsert_state(issue_id, node_id, state=None, check_in_date=None,
                 short_note=None, updated_by_user_id=None,
                 updated_by_name_snapshot=None):
    db = get_db()
    now = _now()
    existing = get_state(issue_id, node_id)
    if existing:
        db.execute(
            """UPDATE issue_node_states
               SET state = ?, check_in_date = ?, short_note = ?,
                   updated_at = ?, updated_by_user_id = ?,
                   updated_by_name_snapshot = ?
               WHERE issue_id = ? AND node_id = ?""",
            (state, check_in_date, short_note, now,
             updated_by_user_id, updated_by_name_snapshot,
             issue_id, node_id),
        )
    else:
        db.execute(
            """INSERT INTO issue_node_states
               (issue_id, node_id, state, check_in_date, short_note,
                updated_at, updated_by_user_id, updated_by_name_snapshot)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (issue_id, node_id, state, check_in_date, short_note,
             now, updated_by_user_id, updated_by_name_snapshot),
        )
    db.commit()
    return get_state(issue_id, node_id)


def get_all_states_for_issues(issue_ids):
    """Bulk load all node states for a list of issue IDs. Returns dict[issue_id][node_id] = row."""
    if not issue_ids:
        return {}
    placeholders = ",".join("?" * len(issue_ids))
    rows = get_db().execute(
        f"SELECT * FROM issue_node_states WHERE issue_id IN ({placeholders})",
        issue_ids,
    ).fetchall()
    result = {}
    for row in rows:
        result.setdefault(row["issue_id"], {})[row["node_id"]] = row
    return result
