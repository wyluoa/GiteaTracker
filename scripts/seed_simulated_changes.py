"""Seed a realistic batch of simulated changes for the /changes page demo.

What it does:
  1. Sets wy's last_viewed_at back to 3 days ago (so /changes has a window).
  2. Clears wy's previous_last_viewed_at (no stale undo button).
  3. Injects ~10 simulated events authored by people-other-than-wy, covering
     every bucket /changes classifies: red-line state change, check-in delay,
     regression, normal progression, new issue, close, field edit.

Re-runnable: each simulated event is tagged with a marker in its body /
closed_note / topic so a re-run wipes the previous batch first.
"""
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import get_db  # noqa: E402 — after sys.path tweak
from app import create_app  # noqa: E402


MARKER = "[SIM]"  # appears in body / note so re-runs can wipe the previous batch

NOW = datetime.now(timezone.utc)


def ts_ago(hours):
    return (NOW - timedelta(hours=hours)).isoformat()


def iso_date_offset(days):
    return (NOW.date() + timedelta(days=days)).isoformat()


def wipe_previous_sim(db):
    """Remove timeline entries + issues + state bumps from a prior run."""
    # Find issues that were created as simulated new issues
    sim_issues = db.execute(
        "SELECT id FROM issues WHERE topic LIKE ?", (f"%{MARKER}%",)
    ).fetchall()
    sim_ids = [r["id"] for r in sim_issues]
    # Delete timeline entries tagged with marker
    db.execute("DELETE FROM timeline_entries WHERE body LIKE ?", (f"%{MARKER}%",))
    db.execute(
        "DELETE FROM timeline_entries WHERE entry_type='field_change' AND new_field_value LIKE ?",
        (f"%{MARKER}%",),
    )
    # Hard-delete simulated issues
    for iid in sim_ids:
        db.execute("DELETE FROM issue_node_states WHERE issue_id = ?", (iid,))
        db.execute("DELETE FROM timeline_entries WHERE issue_id = ?", (iid,))
        db.execute("DELETE FROM issues WHERE id = ?", (iid,))
    # Reopen issues we sim-closed (closed_note marker)
    reopened = db.execute(
        "SELECT id FROM issues WHERE closed_note LIKE ?", (f"%{MARKER}%",)
    ).fetchall()
    for r in reopened:
        db.execute(
            """UPDATE issues SET status='ongoing', closed_at=NULL,
                                 closed_by_user_id=NULL, closed_note=NULL
               WHERE id = ?""",
            (r["id"],),
        )
    db.commit()


def set_wy_baseline(db):
    """Put wy's last_viewed_at 3 days ago, clear undo history."""
    wy = db.execute("SELECT id FROM users WHERE username='wy'").fetchone()
    if not wy:
        raise RuntimeError("user wy not found")
    baseline = ts_ago(72)
    db.execute(
        """UPDATE users
           SET last_viewed_at = ?, previous_last_viewed_at = NULL
           WHERE id = ?""",
        (baseline, wy["id"]),
    )
    db.commit()
    return wy["id"], baseline


def pick_issue(db, above_red=None, min_id=1):
    """Pick an ongoing issue (optionally above/below the red line)."""
    ry = int(db.execute("SELECT value FROM settings WHERE key='red_line_week_year'").fetchone()["value"])
    rw = int(db.execute("SELECT value FROM settings WHERE key='red_line_week_number'").fetchone()["value"])
    if above_red is True:
        row = db.execute(
            """SELECT * FROM issues
               WHERE status='ongoing' AND is_deleted=0 AND id >= ?
                 AND (week_year < ? OR (week_year=? AND week_number <= ?))
               ORDER BY id LIMIT 1""",
            (min_id, ry, ry, rw),
        ).fetchone()
    elif above_red is False:
        row = db.execute(
            """SELECT * FROM issues
               WHERE status='ongoing' AND is_deleted=0 AND id >= ?
                 AND (week_year > ? OR (week_year=? AND week_number > ?))
               ORDER BY id LIMIT 1""",
            (min_id, ry, ry, rw),
        ).fetchone()
    else:
        row = db.execute(
            "SELECT * FROM issues WHERE status='ongoing' AND is_deleted=0 AND id >= ? ORDER BY id LIMIT 1",
            (min_id,),
        ).fetchone()
    return row


def insert_state_change(db, *, issue_id, node_id, old_state, new_state,
                         old_check_in=None, new_check_in=None,
                         author_name, hours_ago, body=None):
    """Insert a simulated state-change timeline entry + update the cell's
    updated_at so the tracker's yellow highlight lights up too."""
    created_at = ts_ago(hours_ago)
    db.execute(
        """INSERT INTO timeline_entries
           (issue_id, entry_type, node_id,
            old_state, new_state, old_check_in_date, new_check_in_date,
            body, author_user_id, author_name_snapshot, created_at)
           VALUES (?, 'state_change', ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
        (issue_id, node_id, old_state, new_state, old_check_in, new_check_in,
         f"{MARKER} {body}" if body else MARKER,
         author_name, created_at),
    )
    # Upsert the cell so tracker agrees
    existing = db.execute(
        "SELECT 1 FROM issue_node_states WHERE issue_id=? AND node_id=?",
        (issue_id, node_id),
    ).fetchone()
    if existing:
        db.execute(
            """UPDATE issue_node_states
               SET state=?, check_in_date=?, updated_at=?,
                   updated_by_user_id=NULL, updated_by_name_snapshot=?
               WHERE issue_id=? AND node_id=?""",
            (new_state, new_check_in, created_at, author_name, issue_id, node_id),
        )
    else:
        db.execute(
            """INSERT INTO issue_node_states
               (issue_id, node_id, state, check_in_date, updated_at,
                updated_by_user_id, updated_by_name_snapshot)
               VALUES (?, ?, ?, ?, ?, NULL, ?)""",
            (issue_id, node_id, new_state, new_check_in, created_at, author_name),
        )


def insert_field_change(db, *, issue_id, field_name, old_value, new_value,
                         author_name, hours_ago):
    created_at = ts_ago(hours_ago)
    # Tag new_value with marker so wipe can find it
    marked_new = f"{new_value} {MARKER}"
    db.execute(
        """INSERT INTO timeline_entries
           (issue_id, entry_type, field_name, old_field_value, new_field_value,
            author_user_id, author_name_snapshot, created_at)
           VALUES (?, 'field_change', ?, ?, ?, NULL, ?, ?)""",
        (issue_id, field_name, old_value, marked_new, author_name, created_at),
    )
    # Also update the issue row so tracker column-highlight matches
    ts_col_map = {
        "topic": "topic_updated_at",
        "requestor_name": "owner_updated_at",
        "jira_ticket": "jira_updated_at",
        "uat_path": "uat_path_updated_at",
    }
    ts_col = ts_col_map.get(field_name)
    if ts_col:
        db.execute(
            f"UPDATE issues SET {field_name}=?, {ts_col}=? WHERE id=?",
            (marked_new, created_at, issue_id),
        )


def create_simulated_new_issue(db, *, display_number, topic, week_year, week_number,
                                requestor_name, hours_ago):
    created_at = ts_ago(hours_ago)
    topic_tagged = f"{topic} {MARKER}"
    cur = db.execute(
        """INSERT INTO issues
           (display_number, topic, requestor_name,
            week_year, week_number, status,
            created_at, created_by_user_id, updated_at, latest_update_at,
            topic_updated_at, owner_updated_at, jira_updated_at, uat_path_updated_at)
           VALUES (?, ?, ?, ?, ?, 'ongoing', ?, NULL, ?, ?, ?, ?, ?, ?)""",
        (display_number, topic_tagged, requestor_name,
         week_year, week_number, created_at, created_at, created_at,
         created_at, created_at, created_at, created_at),
    )
    return cur.lastrowid


def close_simulated_issue(db, *, issue_id, note, author_name, hours_ago):
    closed_at = ts_ago(hours_ago)
    db.execute(
        """UPDATE issues
           SET status='closed', closed_at=?, closed_by_user_id=NULL,
               closed_note=?, updated_at=?
           WHERE id=?""",
        (closed_at, f"{MARKER} {note}", closed_at, issue_id),
    )
    # Also append a comment entry (optional — matches close_issue route)
    db.execute(
        """INSERT INTO timeline_entries
           (issue_id, entry_type, body, author_user_id, author_name_snapshot, created_at)
           VALUES (?, 'comment', ?, NULL, ?, ?)""",
        (issue_id, f"{MARKER} 關單 — {note}", author_name, closed_at),
    )


def main():
    app = create_app()
    with app.app_context():
        db = get_db()
        wipe_previous_sim(db)
        wy_id, baseline = set_wy_baseline(db)

        # Pick target issues ------------------------------------------------
        above_a = pick_issue(db, above_red=True, min_id=1)
        above_b = pick_issue(db, above_red=True, min_id=(above_a["id"] if above_a else 1) + 1)
        above_c = pick_issue(db, above_red=True, min_id=(above_b["id"] if above_b else 1) + 1)
        below_a = pick_issue(db, above_red=False, min_id=1)
        below_b = pick_issue(db, above_red=False, min_id=(below_a["id"] if below_a else 1) + 1)
        below_c = pick_issue(db, above_red=False, min_id=(below_b["id"] if below_b else 1) + 1)
        below_d = pick_issue(db, above_red=False, min_id=(below_c["id"] if below_c else 1) + 1)

        assert above_a and above_b and below_a and below_b, "not enough issues to seed"

        # Nodes — use A10(1), A12(2), N4/N5(7), MtM(10) for variety
        NODE_A10 = 1
        NODE_A12 = 2
        NODE_N45 = 7
        NODE_MTM = 10

        # 1) Red-line state change: above-red issue, Dev → UAT         (important: 紅線)
        insert_state_change(
            db, issue_id=above_a["id"], node_id=NODE_N45,
            old_state="developing", new_state="uat",
            author_name="小王", hours_ago=50,
            body="終於進 UAT 了",
        )

        # 2) Red-line + regression: Done → UAT (requirement walked back)  (important: 紅線 + 退步)
        insert_state_change(
            db, issue_id=above_b["id"], node_id=NODE_A10,
            old_state="done", new_state="uat",
            author_name="小李", hours_ago=40,
            body="需求走回頭路，重做一次 UAT",
        )

        # 3) Check-in delay on a below-red issue (important: 延期)
        insert_state_change(
            db, issue_id=below_a["id"], node_id=NODE_A12,
            old_state="uat", new_state="uat",
            old_check_in=iso_date_offset(-2),
            new_check_in=iso_date_offset(8),
            author_name="阿明", hours_ago=36,
            body="卡在 ChipA 廠商 sample，順延到下週",
        )

        # 4) Same below-red issue, folded: two sequential progressions
        #    Dev → UAT then UAT → UAT done within the window on the MtM node
        insert_state_change(
            db, issue_id=below_a["id"], node_id=NODE_MTM,
            old_state="developing", new_state="uat",
            author_name="阿明", hours_ago=30,
            body="開始 UAT",
        )
        insert_state_change(
            db, issue_id=below_a["id"], node_id=NODE_MTM,
            old_state="uat", new_state="uat_done",
            author_name="阿明", hours_ago=10,
            body="UAT 過了",
        )

        # 5) Normal progression on different below-red issue (non-important)
        insert_state_change(
            db, issue_id=below_b["id"], node_id=NODE_N45,
            old_state="developing", new_state="uat",
            author_name="小王", hours_ago=24,
            body="交接給 QA",
        )

        # 6) Field edit — JIRA ticket added (non-important)
        insert_field_change(
            db, issue_id=below_c["id"] if below_c else below_b["id"],
            field_name="jira_ticket",
            old_value=None,
            new_value="GTRK-1021",
            author_name="Meeting Owner 助理", hours_ago=20,
        )

        # 7) Field edit — UAT Path updated (non-important)
        insert_field_change(
            db, issue_id=below_b["id"],
            field_name="uat_path",
            old_value=None,
            new_value="/uat/checkin/2026-04-22/",
            author_name="小李", hours_ago=18,
        )

        # 8) New issue created by someone else (important: 新題)
        new_id = create_simulated_new_issue(
            db,
            display_number="SIM-001",
            topic="[模擬] 新工具需求：批次 fixture 清理",
            week_year=2026,
            week_number=17,
            requestor_name="外部客戶",
            hours_ago=12,
        )

        # 9) Closed issue (important: 關單)
        if below_d:
            close_simulated_issue(
                db, issue_id=below_d["id"],
                note="已上線 4/22 release",
                author_name="小王", hours_ago=6,
            )

        # 10) Red-line above — further cell TBD → UAT (important: 紅線)
        if above_c:
            insert_state_change(
                db, issue_id=above_c["id"], node_id=NODE_A12,
                old_state="tbd", new_state="uat",
                author_name="小李", hours_ago=4,
                body="外部依賴解掉了，開始做",
            )

        db.commit()

        print(f"OK — wy.last_viewed_at set to {baseline}")
        print(f"     New issue: #{new_id} (SIM-001)")
        print("     Simulated changes live under /changes — look for the [SIM] body marker.")


if __name__ == "__main__":
    main()
