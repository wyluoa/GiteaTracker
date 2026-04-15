"""TimelineEntry model."""
from datetime import datetime, timezone

from app.db import get_db


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_entry(*, issue_id, entry_type, author_user_id=None,
                 author_name_snapshot, node_id=None,
                 old_state=None, new_state=None,
                 old_check_in_date=None, new_check_in_date=None,
                 old_short_note=None, new_short_note=None,
                 body=None, meeting_week_year=None, meeting_week_number=None):
    db = get_db()
    cur = db.execute(
        """INSERT INTO timeline_entries
           (issue_id, entry_type, node_id,
            old_state, new_state, old_check_in_date, new_check_in_date,
            old_short_note, new_short_note, body,
            meeting_week_year, meeting_week_number,
            author_user_id, author_name_snapshot, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (issue_id, entry_type, node_id,
         old_state, new_state, old_check_in_date, new_check_in_date,
         old_short_note, new_short_note, body,
         meeting_week_year, meeting_week_number,
         author_user_id, author_name_snapshot, _now()),
    )
    db.commit()
    return cur.lastrowid


def get_for_issue(issue_id, entry_type=None, node_id=None):
    db = get_db()
    sql = "SELECT * FROM timeline_entries WHERE issue_id = ?"
    params = [issue_id]

    if entry_type:
        sql += " AND entry_type = ?"
        params.append(entry_type)

    if node_id:
        # Show entries for this node + entries without a node (comments, meeting notes)
        sql += " AND (node_id = ? OR node_id IS NULL)"
        params.append(node_id)

    sql += " ORDER BY created_at DESC"
    entries = db.execute(sql, params).fetchall()

    # Load attachments for each entry
    entry_ids = [e["id"] for e in entries]
    attachments_map = {}
    if entry_ids:
        placeholders = ",".join("?" * len(entry_ids))
        atts = db.execute(
            f"SELECT * FROM attachments WHERE timeline_entry_id IN ({placeholders})",
            entry_ids,
        ).fetchall()
        for a in atts:
            attachments_map.setdefault(a["timeline_entry_id"], []).append(a)

    # Convert to dicts so we can add attachments
    result = []
    for e in entries:
        d = dict(e)
        d["attachments"] = attachments_map.get(e["id"], [])
        result.append(d)
    return result
