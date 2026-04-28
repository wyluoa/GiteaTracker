"""Issue model — CRUD + filtering + cache updates."""
from datetime import datetime, timezone, date

from app.db import get_db


def _now():
    return datetime.now(timezone.utc).isoformat()


# Which per-field timestamp to bump when a given issues column changes.
# Drives tracker.html row-level highlight per column.
FIELD_TO_TS = {
    "topic": "topic_updated_at",
    "requestor_name": "owner_updated_at",
    "requestor_user_id": "owner_updated_at",
    "owner_user_id": "owner_updated_at",
    "jira_ticket": "jira_updated_at",
    "uat_path": "uat_path_updated_at",
}

# Canonical user-facing fields tracked in /changes summary. Only these emit
# field_change timeline entries (avoids double-logging for user_id variants
# that point at the same timestamp column).
_FIELD_CHANGE_LOGGED = ("display_number", "topic", "requestor_name", "jira_ticket", "uat_path")


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
            created_at, created_by_user_id, updated_at, latest_update_at,
            topic_updated_at, owner_updated_at, jira_updated_at, uat_path_updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (display_number, topic, requestor_user_id, requestor_name,
         owner_user_id, week_year, week_number, jira_ticket, icv,
         uat_path, gitea_issue_url, status,
         now, created_by_user_id, now, now,
         now, now, now, now),
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


def get_all_closed():
    """All closed issues (no pagination), ordered by week for the Excel
    export's Closed sheet. Sorted week-old → week-new to match Ongoing's
    layout, since the export reader scans week by week."""
    return get_db().execute(
        """SELECT * FROM issues
           WHERE status = 'closed' AND is_deleted = 0
           ORDER BY week_year, week_number, CAST(display_number AS INTEGER)"""
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


def list_ready_to_close():
    return get_db().execute(
        """SELECT id, display_number, topic FROM issues
           WHERE status = 'ongoing' AND all_nodes_done = 1 AND is_deleted = 0
           ORDER BY display_number"""
    ).fetchall()


def count_pending_close():
    row = get_db().execute(
        "SELECT COUNT(*) as cnt FROM issues WHERE status = 'ongoing' AND pending_close = 1 AND is_deleted = 0"
    ).fetchone()
    return row["cnt"]


def list_pending_close():
    return get_db().execute(
        """SELECT id, display_number, topic FROM issues
           WHERE status = 'ongoing' AND pending_close = 1 AND is_deleted = 0
           ORDER BY display_number"""
    ).fetchall()


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


def uat_tbd_above_redline_per_node(red_line_year, red_line_week, with_jira=False):
    """Per-node count of ongoing issues above red line in UAT/TBD state.

    UAT done is excluded — those are already tested and waiting to go live,
    not the "still stuck" issues this count is meant to surface.

    with_jira=True restricts to issues whose jira_ticket is set.
    """
    if not red_line_year or not red_line_week:
        return {}
    db = get_db()
    jira_clause = "AND i.jira_ticket IS NOT NULL AND TRIM(i.jira_ticket) != ''" if with_jira else ""
    rows = db.execute(
        f"""SELECT s.node_id, COUNT(DISTINCT i.id) as cnt
            FROM issues i
            JOIN issue_node_states s ON i.id = s.issue_id
            WHERE i.status = 'ongoing' AND i.is_deleted = 0
              AND s.state IN ('uat', 'tbd')
              AND (i.week_year < ? OR (i.week_year = ? AND i.week_number <= ?))
              {jira_clause}
            GROUP BY s.node_id""",
        (red_line_year, red_line_year, red_line_week),
    ).fetchall()
    return {r["node_id"]: r["cnt"] for r in rows}


def weekly_trend_summary():
    """Summary sentence data: latest vs previous row of weekly_trend_data.

    Returns {'latest': {...} | None, 'prev': {...} | None}. Each bucket has
    total / developing / uat_tbd / closed / week_year / week_number.
    """
    db = get_db()
    rows = db.execute(
        """SELECT week_year, week_number, cnt_uat, cnt_tbd, cnt_dev, cnt_close
           FROM weekly_trend_data
           ORDER BY week_year DESC, week_number DESC
           LIMIT 2"""
    ).fetchall()

    def _bucket(r):
        return {
            "week_year": r["week_year"],
            "week_number": r["week_number"],
            "total": r["cnt_uat"] + r["cnt_tbd"] + r["cnt_dev"] + r["cnt_close"],
            "developing": r["cnt_dev"],
            "uat_tbd": r["cnt_uat"] + r["cnt_tbd"],
            "closed": r["cnt_close"],
        }

    latest = _bucket(rows[0]) if len(rows) >= 1 else None
    prev = _bucket(rows[1]) if len(rows) >= 2 else None
    return {"latest": latest, "prev": prev}


def closing_rate_excluding_node(exclude_code="n_mtm"):
    """Closing rate treating issues as 'done' when all nodes EXCEPT the
    excluded node are done/unneeded.

    Returns (rate_pct, effectively_closed, total).
    """
    db = get_db()

    excluded = db.execute(
        "SELECT id FROM nodes WHERE code = ?", (exclude_code,)
    ).fetchone()
    exclude_id = excluded["id"] if excluded else -1

    # All active non-excluded node IDs
    required_nodes = db.execute(
        "SELECT id FROM nodes WHERE is_active = 1 AND id != ?", (exclude_id,)
    ).fetchall()
    required_ids = {r["id"] for r in required_nodes}
    n_required = len(required_ids)

    # Already closed
    closed = db.execute(
        "SELECT COUNT(*) as cnt FROM issues WHERE status = 'closed' AND is_deleted = 0"
    ).fetchone()["cnt"]

    total = db.execute(
        "SELECT COUNT(*) as cnt FROM issues WHERE is_deleted = 0"
    ).fetchone()["cnt"]

    # Ongoing issues where every required node is done/unneeded
    placeholders = ",".join("?" * n_required)
    rows = db.execute(
        f"""SELECT i.id
            FROM issues i
            WHERE i.status = 'ongoing' AND i.is_deleted = 0
              AND (
                SELECT COUNT(*)
                FROM issue_node_states s
                WHERE s.issue_id = i.id
                  AND s.node_id IN ({placeholders})
                  AND s.state IN ('done', 'unneeded')
              ) = ?""",
        list(required_ids) + [n_required],
    ).fetchall()
    ready_without_excluded = len(rows)

    effectively_closed = closed + ready_without_excluded
    rate = round(effectively_closed / total * 100, 1) if total else 0
    return rate, effectively_closed, total


def count_node_states_by_type(state_type):
    """Per-node count of ongoing issues in a given state (e.g. 'uat', 'tbd').

    For 'uat', also counts 'uat_done'.
    Returns (total, {node_id: count}).
    """
    db = get_db()
    if state_type == "uat":
        state_filter = "s.state IN ('uat', 'uat_done')"
    else:
        state_filter = "s.state = ?"

    sql = f"""SELECT s.node_id, COUNT(DISTINCT i.id) as cnt
              FROM issues i
              JOIN issue_node_states s ON i.id = s.issue_id
              WHERE i.status = 'ongoing' AND i.is_deleted = 0
                AND {state_filter}
              GROUP BY s.node_id"""

    if state_type == "uat":
        rows = db.execute(sql).fetchall()
    else:
        rows = db.execute(sql, (state_type,)).fetchall()

    per_node = {r["node_id"]: r["cnt"] for r in rows}
    total = sum(per_node.values())
    return total, per_node


def update_issue(issue_id, *, author_user_id=None, author_name_snapshot=None,
                 **fields):
    """Update arbitrary fields on an issue.

    Auto-bumps per-field timestamps (FIELD_TO_TS) so the tracker can highlight
    exactly the column(s) that changed, independent of other meta edits.

    When author_user_id + author_name_snapshot are provided, also append a
    field_change timeline entry for each canonical tracked field that actually
    changed (topic/requestor_name/jira_ticket/uat_path). Callers that don't
    represent a human edit (bulk import, soft delete, close/reopen) can omit
    them to skip the log.
    """
    if not fields:
        return
    will_log = (author_user_id is not None and author_name_snapshot is not None)
    old_row = get_by_id(issue_id) if will_log else None

    now = _now()
    fields["updated_at"] = now
    for key in list(fields.keys()):
        ts_col = FIELD_TO_TS.get(key)
        if ts_col and ts_col not in fields:
            fields[ts_col] = now
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [issue_id]
    db = get_db()
    db.execute(f"UPDATE issues SET {set_clause} WHERE id = ?", vals)
    db.commit()

    if will_log and old_row is not None:
        from app.models import timeline as timeline_model
        for key in _FIELD_CHANGE_LOGGED:
            if key not in fields:
                continue
            old_val = old_row[key] if key in old_row.keys() else None
            new_val = fields[key]
            if (old_val or "") == (new_val or ""):
                continue
            timeline_model.create_entry(
                issue_id=issue_id,
                entry_type="field_change",
                field_name=key,
                old_field_value=(str(old_val) if old_val is not None else None),
                new_field_value=(str(new_val) if new_val is not None else None),
                author_user_id=author_user_id,
                author_name_snapshot=author_name_snapshot,
            )


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
        # Only bump latest_update_at / all_nodes_done here. issues.updated_at is
        # reserved for meta-field changes (topic/owner/jira/uat_path/...) so the
        # tracker can highlight those columns distinctly from per-cell changes.
        db.execute(
            "UPDATE issues SET latest_update_at = ?, all_nodes_done = ? WHERE id = ?",
            (row["latest"], row["all_done"] or 0, issue_id),
        )
        db.commit()


def current_phase_snapshot():
    """Snapshot the current count of all live issues split into UAT/TBD/Dev/Close.

    Priority-ordered, each issue lands in exactly one bucket (first match wins):
      1. Close: status = 'closed'
      2. UAT:   any node state = 'uat'   (uat_done is NOT UAT — UAT means
                                           "still needs testing"; once tested it
                                           drops out)
      3. TBD:   any node state = 'tbd'
      4. Dev:   everything else (catch-all: developing-only, all blank,
                                  uat_done, all done/unneeded but not closed,
                                  on_hold without uat/tbd)

    Used by the Dashboard "本週快照" hint to tell the user what numbers to
    record this week in Admin → Trend Data. The cumulative chart itself reads
    weekly_trend_data, not this snapshot.
    """
    db = get_db()

    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()

    issues = db.execute(
        "SELECT id, status FROM issues WHERE is_deleted = 0"
    ).fetchall()

    snapshot = {"UAT": 0, "TBD": 0, "Dev": 0, "Close": 0,
                "week_year": iso_year, "week_number": iso_week}
    snapshot["total"] = 0

    if not issues:
        return snapshot

    issue_ids = [i["id"] for i in issues]
    ph = ",".join("?" * len(issue_ids))
    state_rows = db.execute(
        f"""SELECT issue_id,
                   MAX(CASE WHEN state = 'uat' THEN 3
                            WHEN state = 'tbd' THEN 2
                            ELSE 0 END) as max_phase
            FROM issue_node_states
            WHERE issue_id IN ({ph})
            GROUP BY issue_id""",
        issue_ids,
    ).fetchall()
    phase_map = {r["issue_id"]: r["max_phase"] for r in state_rows}

    for i in issues:
        if i["status"] == "closed":
            snapshot["Close"] += 1
            continue
        mp = phase_map.get(i["id"], 0)
        if mp == 3:
            snapshot["UAT"] += 1
        elif mp == 2:
            snapshot["TBD"] += 1
        else:
            snapshot["Dev"] += 1

    snapshot["total"] = (snapshot["UAT"] + snapshot["TBD"]
                         + snapshot["Dev"] + snapshot["Close"])
    return snapshot


def get_bottleneck_nodes():
    """For each ongoing issue, find which nodes are the sole blockers
    (not done/unneeded). Count how many times each node is a blocker
    when only 1-2 nodes remain.

    Returns {node_id: count} — higher = bigger bottleneck.
    """
    db = get_db()
    # Get ongoing issues and their incomplete nodes
    rows = db.execute(
        """SELECT i.id as issue_id, s.node_id
           FROM issues i
           JOIN issue_node_states s ON i.id = s.issue_id
           WHERE i.status = 'ongoing' AND i.is_deleted = 0
             AND s.state NOT IN ('done', 'unneeded')"""
    ).fetchall()

    # Also count issues with nodes that have no state record (blank = incomplete)
    all_nodes = db.execute(
        "SELECT id FROM nodes WHERE is_active = 1"
    ).fetchall()
    all_node_ids = {n["id"] for n in all_nodes}

    ongoing_ids = db.execute(
        "SELECT id FROM issues WHERE status = 'ongoing' AND is_deleted = 0"
    ).fetchall()

    # Build incomplete-nodes map per issue
    # Start with explicit non-done states
    incomplete = {}
    for r in rows:
        incomplete.setdefault(r["issue_id"], set()).add(r["node_id"])

    # Add nodes with no state record at all (blank cells)
    stated_nodes = {}
    state_rows = db.execute(
        """SELECT s.issue_id, s.node_id
           FROM issue_node_states s
           JOIN issues i ON i.id = s.issue_id
           WHERE i.status = 'ongoing' AND i.is_deleted = 0"""
    ).fetchall()
    for r in state_rows:
        stated_nodes.setdefault(r["issue_id"], set()).add(r["node_id"])

    for oi in ongoing_ids:
        iid = oi["id"]
        stated = stated_nodes.get(iid, set())
        missing = all_node_ids - stated
        if missing:
            incomplete.setdefault(iid, set()).update(missing)

    # Count: for issues with 1-2 remaining nodes, tally each blocking node
    bottleneck = {}
    for iid, node_set in incomplete.items():
        if 1 <= len(node_set) <= 2:
            for nid in node_set:
                bottleneck[nid] = bottleneck.get(nid, 0) + 1

    return bottleneck


def get_weekly_velocity():
    """New issues created vs closed per week.

    Returns {weeks: [...], created: [...], closed: [...]}.
    """
    db = get_db()

    # Created per week (using week_year/week_number)
    created_rows = db.execute(
        """SELECT week_year, week_number, COUNT(*) as cnt
           FROM issues WHERE is_deleted = 0
           GROUP BY week_year, week_number
           ORDER BY week_year, week_number"""
    ).fetchall()

    # Closed per week (using closed_at date → ISO week)
    closed_rows = db.execute(
        """SELECT closed_at FROM issues
           WHERE status = 'closed' AND is_deleted = 0 AND closed_at IS NOT NULL"""
    ).fetchall()

    closed_by_week = {}
    for r in closed_rows:
        try:
            dt = datetime.fromisoformat(r["closed_at"])
            iso = dt.date().isocalendar()
            key = (iso[0], iso[1])
            closed_by_week[key] = closed_by_week.get(key, 0) + 1
        except (ValueError, TypeError):
            pass

    # Merge all weeks
    all_weeks = set()
    for r in created_rows:
        all_weeks.add((r["week_year"], r["week_number"]))
    all_weeks.update(closed_by_week.keys())
    all_weeks = sorted(all_weeks)

    created_map = {(r["week_year"], r["week_number"]): r["cnt"] for r in created_rows}

    weeks = []
    created = []
    closed = []
    for wk in all_weeks:
        weeks.append(f"wk{wk[0] - 2020}{wk[1]:02d}")
        created.append(created_map.get(wk, 0))
        closed.append(closed_by_week.get(wk, 0))

    return {"weeks": weeks, "created": created, "closed": closed}


def get_aging_stats():
    """Compute aging statistics for issues.

    Returns dict with:
      - avg_days_to_close: average days from creation to close
      - stale_issues: list of ongoing issues not updated in 14+ days
    """
    db = get_db()
    today = date.today()

    # Average days to close
    closed_rows = db.execute(
        """SELECT created_at, closed_at FROM issues
           WHERE status = 'closed' AND is_deleted = 0
             AND closed_at IS NOT NULL AND created_at IS NOT NULL"""
    ).fetchall()

    days_list = []
    for r in closed_rows:
        try:
            c = datetime.fromisoformat(r["created_at"]).date()
            d = datetime.fromisoformat(r["closed_at"]).date()
            days_list.append((d - c).days)
        except (ValueError, TypeError):
            pass

    avg_days = round(sum(days_list) / len(days_list), 1) if days_list else 0

    # Stale ongoing issues (no update in 14+ days)
    stale_rows = db.execute(
        """SELECT id, display_number, topic, requestor_name,
                  week_year, week_number, latest_update_at, created_at
           FROM issues
           WHERE status = 'ongoing' AND is_deleted = 0
           ORDER BY latest_update_at ASC"""
    ).fetchall()

    stale = []
    for r in stale_rows:
        try:
            last = datetime.fromisoformat(r["latest_update_at"] or r["created_at"]).date()
            age_days = (today - last).days
            if age_days >= 90:
                stale.append({
                    "id": r["id"],
                    "display_number": r["display_number"],
                    "topic": r["topic"],
                    "requestor_name": r["requestor_name"],
                    "week_label": f"wk{r['week_year'] - 2020}{r['week_number']:02d}",
                    "days_stale": age_days,
                })
        except (ValueError, TypeError):
            pass

    return {"avg_days_to_close": avg_days, "stale_issues": stale}


def get_almost_done_issues(max_remaining=2):
    """Find ongoing issues where only 1-2 active nodes are NOT done/unneeded.

    Returns list of dicts with issue info + remaining node names.
    """
    db = get_db()

    all_nodes = db.execute(
        "SELECT id, display_name FROM nodes WHERE is_active = 1"
    ).fetchall()
    all_node_ids = {n["id"] for n in all_nodes}
    node_names = {n["id"]: n["display_name"] for n in all_nodes}
    n_total = len(all_node_ids)

    # Count done/unneeded nodes per ongoing issue
    rows = db.execute(
        """SELECT i.id, i.display_number, i.topic, i.requestor_name,
                  i.week_year, i.week_number,
                  COUNT(CASE WHEN s.state IN ('done', 'unneeded') THEN 1 END) as done_cnt
           FROM issues i
           LEFT JOIN issue_node_states s ON i.id = s.issue_id
             AND s.node_id IN (SELECT id FROM nodes WHERE is_active = 1)
           WHERE i.status = 'ongoing' AND i.is_deleted = 0
           GROUP BY i.id
           HAVING ? - done_cnt BETWEEN 1 AND ?""",
        (n_total, max_remaining),
    ).fetchall()

    result = []
    for r in rows:
        # Find which nodes are still incomplete
        done_nodes = db.execute(
            """SELECT node_id FROM issue_node_states
               WHERE issue_id = ? AND state IN ('done', 'unneeded')""",
            (r["id"],),
        ).fetchall()
        done_ids = {d["node_id"] for d in done_nodes}
        remaining_ids = all_node_ids - done_ids
        remaining_names = [node_names[nid] for nid in sorted(remaining_ids)]

        result.append({
            "id": r["id"],
            "display_number": r["display_number"],
            "topic": r["topic"],
            "requestor_name": r["requestor_name"],
            "week_label": f"wk{r['week_year'] - 2020}{r['week_number']:02d}",
            "remaining_count": len(remaining_names),
            "remaining_nodes": remaining_names,
        })

    # Sort: fewest remaining first
    result.sort(key=lambda x: (x["remaining_count"], x["display_number"]))
    return result
