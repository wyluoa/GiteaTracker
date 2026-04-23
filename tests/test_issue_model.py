"""
issue_model.update_issue + refresh_cache + field_change timeline:

  - Updating a tracked field bumps ONLY that field's timestamp column
  - Updating an untracked field (status, closed_note) does NOT bump any
    per-field timestamp
  - Bumping order: updated_at always gets the latest; latest_update_at
    (cache column) is reserved for cell changes via refresh_cache — NOT
    for meta-field edits
  - refresh_cache computes all_nodes_done = 1 iff every cell in
    (done, unneeded) and there's at least one cell
  - Passing author_user_id + author_name_snapshot writes a
    field_change timeline entry; omitting them does NOT
"""
from datetime import datetime, timezone
import time

from app.models import issue as issue_model


def _now():
    return datetime.now(timezone.utc).isoformat()


def _fetch(db, iid):
    return dict(db.execute("SELECT * FROM issues WHERE id = ?", (iid,)).fetchone())


# ─── Per-field timestamps ─────────────────────────────────────────────

def test_update_issue_bumps_only_affected_field_ts(app, db, sample_issue):
    iid = sample_issue()
    before = _fetch(db, iid)
    time.sleep(0.01)  # guarantee monotonic ts diff on fast machines

    with app.app_context():
        issue_model.update_issue(iid, jira_ticket="JIRA-100")

    after = _fetch(db, iid)
    # jira_updated_at advanced
    assert after["jira_updated_at"] > before["jira_updated_at"]
    # other per-field ts columns unchanged
    assert after["topic_updated_at"] == before["topic_updated_at"]
    assert after["owner_updated_at"] == before["owner_updated_at"]
    assert after["uat_path_updated_at"] == before["uat_path_updated_at"]
    # issues.updated_at bumped (every update advances it)
    assert after["updated_at"] > before["updated_at"]


def test_update_issue_topic_bumps_topic_ts_only(app, db, sample_issue):
    iid = sample_issue()
    before = _fetch(db, iid)
    time.sleep(0.01)
    with app.app_context():
        issue_model.update_issue(iid, topic="new topic")
    after = _fetch(db, iid)
    assert after["topic_updated_at"] > before["topic_updated_at"]
    assert after["jira_updated_at"] == before["jira_updated_at"]
    assert after["owner_updated_at"] == before["owner_updated_at"]


def test_update_issue_owner_bumps_owner_ts(app, db, sample_issue):
    iid = sample_issue()
    before = _fetch(db, iid)
    time.sleep(0.01)
    with app.app_context():
        issue_model.update_issue(iid, requestor_name="bob")
    after = _fetch(db, iid)
    assert after["owner_updated_at"] > before["owner_updated_at"]
    assert after["topic_updated_at"] == before["topic_updated_at"]


def test_update_issue_untracked_field_does_not_bump_field_ts(app, db, sample_issue):
    """closed_note is NOT in FIELD_TO_TS — updating it should NOT bump any
    per-field timestamp, only the general updated_at."""
    iid = sample_issue()
    before = _fetch(db, iid)
    time.sleep(0.01)
    with app.app_context():
        issue_model.update_issue(iid, closed_note="some reason")
    after = _fetch(db, iid)
    assert after["updated_at"] > before["updated_at"]
    assert after["topic_updated_at"] == before["topic_updated_at"]
    assert after["jira_updated_at"] == before["jira_updated_at"]
    assert after["owner_updated_at"] == before["owner_updated_at"]
    assert after["uat_path_updated_at"] == before["uat_path_updated_at"]


def test_update_issue_latest_update_at_unchanged_by_meta_edits(app, db, sample_issue):
    """CLAUDE.md rule: meta-field edits must NOT pollute latest_update_at.
    That column is reserved for cell changes + refresh_cache."""
    iid = sample_issue()
    before = _fetch(db, iid)
    time.sleep(0.01)
    with app.app_context():
        issue_model.update_issue(iid, jira_ticket="JIRA-200")
    after = _fetch(db, iid)
    assert after["latest_update_at"] == before["latest_update_at"]


# ─── refresh_cache ────────────────────────────────────────────────────

def test_refresh_cache_all_nodes_done(app, db, sample_issue, nodes):
    iid = sample_issue()
    # Set every node to 'done'
    now = _now()
    for n in nodes:
        db.execute(
            """INSERT INTO issue_node_states
               (issue_id, node_id, state, updated_at, updated_by_user_id, updated_by_name_snapshot)
               VALUES (?, ?, 'done', ?, NULL, 'tester')""",
            (iid, n["id"], now),
        )
    db.commit()
    with app.app_context():
        issue_model.refresh_cache(iid)
    row = _fetch(db, iid)
    assert row["all_nodes_done"] == 1


def test_refresh_cache_mixed_states_not_all_done(app, db, sample_issue, nodes):
    iid = sample_issue()
    now = _now()
    # half 'done', half 'uat'
    for i, n in enumerate(nodes):
        state = "done" if i % 2 == 0 else "uat"
        db.execute(
            """INSERT INTO issue_node_states
               (issue_id, node_id, state, updated_at, updated_by_user_id, updated_by_name_snapshot)
               VALUES (?, ?, ?, ?, NULL, 'tester')""",
            (iid, n["id"], state, now),
        )
    db.commit()
    with app.app_context():
        issue_model.refresh_cache(iid)
    row = _fetch(db, iid)
    assert row["all_nodes_done"] == 0


def test_refresh_cache_unneeded_counts_as_done(app, db, sample_issue, nodes):
    iid = sample_issue()
    now = _now()
    # mix of done + unneeded across all nodes → should still be all_nodes_done = 1
    for i, n in enumerate(nodes):
        state = "unneeded" if i % 3 == 0 else "done"
        db.execute(
            """INSERT INTO issue_node_states
               (issue_id, node_id, state, updated_at, updated_by_user_id, updated_by_name_snapshot)
               VALUES (?, ?, ?, ?, NULL, 'tester')""",
            (iid, n["id"], state, now),
        )
    db.commit()
    with app.app_context():
        issue_model.refresh_cache(iid)
    row = _fetch(db, iid)
    assert row["all_nodes_done"] == 1


def test_refresh_cache_latest_update_at_is_max_cell_updated_at(app, db, sample_issue, nodes):
    iid = sample_issue()
    # Insert 2 cells with distinct updated_at
    early = "2026-01-01T00:00:00+00:00"
    late  = "2026-03-15T12:00:00+00:00"
    db.execute(
        """INSERT INTO issue_node_states (issue_id, node_id, state, updated_at,
                                           updated_by_user_id, updated_by_name_snapshot)
           VALUES (?, ?, 'uat', ?, NULL, 'a')""",
        (iid, nodes[0]["id"], early),
    )
    db.execute(
        """INSERT INTO issue_node_states (issue_id, node_id, state, updated_at,
                                           updated_by_user_id, updated_by_name_snapshot)
           VALUES (?, ?, 'done', ?, NULL, 'b')""",
        (iid, nodes[1]["id"], late),
    )
    db.commit()
    with app.app_context():
        issue_model.refresh_cache(iid)
    row = _fetch(db, iid)
    assert row["latest_update_at"] == late


# ─── field_change timeline entries ────────────────────────────────────

def test_update_issue_with_author_writes_field_change(app, db, sample_issue, make_user):
    author = make_user("alice")
    iid = sample_issue(jira_ticket="JIRA-OLD")
    with app.app_context():
        issue_model.update_issue(
            iid, jira_ticket="JIRA-NEW",
            author_user_id=author["id"], author_name_snapshot="alice",
        )

    rows = db.execute(
        "SELECT * FROM timeline_entries WHERE issue_id=? AND entry_type='field_change'",
        (iid,),
    ).fetchall()
    assert len(rows) == 1
    r = dict(rows[0])
    assert r["field_name"] == "jira_ticket"
    assert r["old_field_value"] == "JIRA-OLD"
    assert r["new_field_value"] == "JIRA-NEW"
    assert r["author_name_snapshot"] == "alice"


def test_update_issue_without_author_skips_field_change(app, db, sample_issue):
    """No author context → no timeline row. Used for bulk import / soft
    delete / close / reopen paths that don't represent a user edit of
    the logical field."""
    iid = sample_issue(jira_ticket="JIRA-OLD")
    with app.app_context():
        issue_model.update_issue(iid, jira_ticket="JIRA-NEW")  # no author kw
    rows = db.execute(
        "SELECT * FROM timeline_entries WHERE issue_id=? AND entry_type='field_change'",
        (iid,),
    ).fetchall()
    assert rows == []


def test_update_issue_no_actual_change_skips_field_change(app, db, sample_issue, make_user):
    """Passing the same value → no field_change entry (no real edit)."""
    author = make_user("alice")
    iid = sample_issue(jira_ticket="JIRA-SAME")
    with app.app_context():
        issue_model.update_issue(
            iid, jira_ticket="JIRA-SAME",
            author_user_id=author["id"], author_name_snapshot="alice",
        )
    rows = db.execute(
        "SELECT * FROM timeline_entries WHERE issue_id=? AND entry_type='field_change'",
        (iid,),
    ).fetchall()
    assert rows == []


def test_update_issue_multi_field_writes_one_entry_per_tracked_field(app, db, sample_issue, make_user):
    """Updating topic + uat_path in one call → two field_change rows.
    Non-tracked fields in the same call (status, closed_note) → ignored."""
    author = make_user("alice")
    iid = sample_issue(topic="old topic", uat_path=None)
    with app.app_context():
        issue_model.update_issue(
            iid,
            topic="new topic",
            uat_path="/x/y/z",
            closed_note="ignored",   # not a logged field
            author_user_id=author["id"], author_name_snapshot="alice",
        )
    rows = db.execute(
        """SELECT field_name FROM timeline_entries
           WHERE issue_id=? AND entry_type='field_change'
           ORDER BY id""",
        (iid,),
    ).fetchall()
    names = {r["field_name"] for r in rows}
    assert names == {"topic", "uat_path"}


def test_update_issue_none_to_value_records_as_null_old(app, db, sample_issue, make_user):
    author = make_user("alice")
    iid = sample_issue(jira_ticket=None)
    with app.app_context():
        issue_model.update_issue(
            iid, jira_ticket="JIRA-1",
            author_user_id=author["id"], author_name_snapshot="alice",
        )
    r = db.execute(
        "SELECT * FROM timeline_entries WHERE issue_id=? AND entry_type='field_change'",
        (iid,),
    ).fetchone()
    assert r["old_field_value"] is None
    assert r["new_field_value"] == "JIRA-1"


def test_update_issue_value_to_none_records_as_null_new(app, db, sample_issue, make_user):
    author = make_user("alice")
    iid = sample_issue(jira_ticket="JIRA-OLD")
    with app.app_context():
        issue_model.update_issue(
            iid, jira_ticket=None,
            author_user_id=author["id"], author_name_snapshot="alice",
        )
    r = db.execute(
        "SELECT * FROM timeline_entries WHERE issue_id=? AND entry_type='field_change'",
        (iid,),
    ).fetchone()
    assert r["old_field_value"] == "JIRA-OLD"
    assert r["new_field_value"] is None
