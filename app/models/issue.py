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
