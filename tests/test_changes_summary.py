"""
changes_summary.build_summary — aggregation, folding, severity flags,
filter_node_id, include_own.

Covers:
  - Basic event pickup (state_change / field_change / new_issue / closed)
  - Folding multiple state_changes on the same cell → one event with fold_count
  - Severity flagging: red-line, regression, check-in delay
  - include_own toggles exclude of current-user-authored events
  - filter_node_id restricts to one node AND drops field_change / new_issue / closed
"""
from datetime import datetime, timezone, timedelta

import pytest

from app.models import changes_summary


ONE_HOUR = timedelta(hours=1)


def _iso(dt):
    return dt.isoformat()


def _insert_state_change(db, *, issue_id, node_id, old_state, new_state,
                          old_check_in=None, new_check_in=None,
                          author_user_id=None, author_name="alice",
                          created_at=None, body=None):
    db.execute(
        """INSERT INTO timeline_entries
           (issue_id, entry_type, node_id,
            old_state, new_state, old_check_in_date, new_check_in_date,
            body, author_user_id, author_name_snapshot, created_at)
           VALUES (?, 'state_change', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (issue_id, node_id, old_state, new_state,
         old_check_in, new_check_in, body,
         author_user_id, author_name, created_at or _iso(datetime.now(timezone.utc))),
    )
    db.commit()


def _insert_field_change(db, *, issue_id, field_name, old_value, new_value,
                          author_user_id=None, author_name="alice",
                          created_at=None):
    db.execute(
        """INSERT INTO timeline_entries
           (issue_id, entry_type, field_name, old_field_value, new_field_value,
            author_user_id, author_name_snapshot, created_at)
           VALUES (?, 'field_change', ?, ?, ?, ?, ?, ?)""",
        (issue_id, field_name, old_value, new_value,
         author_user_id, author_name, created_at or _iso(datetime.now(timezone.utc))),
    )
    db.commit()


# ─── Basic pickup ──────────────────────────────────────────────────────

def test_cell_state_change_shows_up(app, db, old_issue, nodes, make_user):
    user = make_user("viewer")
    other = make_user("other")
    iid = old_issue()
    since = _iso(datetime.now(timezone.utc) - ONE_HOUR)

    _insert_state_change(db, issue_id=iid, node_id=nodes[0]["id"],
                         old_state=None, new_state="uat",
                         author_user_id=other["id"])

    with app.app_context():
        s = changes_summary.build_summary(
            current_user_id=user["id"], since=since, include_own=False,
        )
    assert s["counts"]["total_events"] == 1
    assert s["issues"][0]["events"][0]["type"] == "cell"


def test_field_change_shows_up(app, db, old_issue, make_user):
    user = make_user("viewer")
    other = make_user("other")
    iid = old_issue()
    since = _iso(datetime.now(timezone.utc) - ONE_HOUR)

    _insert_field_change(db, issue_id=iid, field_name="jira_ticket",
                         old_value=None, new_value="JIRA-1",
                         author_user_id=other["id"])

    with app.app_context():
        s = changes_summary.build_summary(
            current_user_id=user["id"], since=since, include_own=False,
        )
    events = s["issues"][0]["events"]
    assert len(events) == 1
    assert events[0]["type"] == "field"
    assert events[0]["field_name"] == "jira_ticket"


def test_new_issue_and_closed_pickups(app, db, sample_issue, make_user):
    user = make_user("viewer")
    other = make_user("other")
    since_dt = datetime.now(timezone.utc) - ONE_HOUR
    since = _iso(since_dt)

    # An issue created after `since`
    later = _iso(datetime.now(timezone.utc))
    db.execute(
        """UPDATE issues SET created_at=?, created_by_user_id=?
           WHERE id=?""",
        (later, other["id"], sample_issue()),
    )
    # A separately closed issue
    closed_iid = sample_issue(display_number="C1")
    db.execute(
        """UPDATE issues SET status='closed', closed_at=?, closed_by_user_id=?
           WHERE id=?""",
        (later, other["id"], closed_iid),
    )
    db.commit()

    with app.app_context():
        s = changes_summary.build_summary(
            current_user_id=user["id"], since=since, include_own=False,
        )
    counts = s["counts"]
    assert counts["new_issues"] >= 1
    assert counts["closed_issues"] >= 1


# ─── Folding ──────────────────────────────────────────────────────────

def test_multiple_cell_changes_fold_to_one_event(app, db, sample_issue, nodes, make_user):
    user = make_user("viewer")
    other = make_user("other")
    iid = sample_issue()
    since_dt = datetime.now(timezone.utc) - ONE_HOUR
    since = _iso(since_dt)

    # 3 changes on same cell
    for i, (old, new) in enumerate([("developing", "uat"),
                                     ("uat", "uat_done"),
                                     ("uat_done", "done")]):
        t = _iso(since_dt + timedelta(minutes=10 * (i + 1)))
        _insert_state_change(db, issue_id=iid, node_id=nodes[0]["id"],
                             old_state=old, new_state=new,
                             author_user_id=other["id"],
                             created_at=t)

    with app.app_context():
        s = changes_summary.build_summary(
            current_user_id=user["id"], since=since, include_own=False,
        )
    ev = s["issues"][0]["events"][0]
    assert ev["fold_count"] == 3
    assert ev["old_state"] == "developing"   # earliest
    assert ev["new_state"] == "done"         # latest


# ─── Severity flags ───────────────────────────────────────────────────

def test_red_line_flag_fires_on_above_red_issue(app, db, sample_issue, nodes, make_user, set_red_line):
    user = make_user("viewer")
    other = make_user("other")
    set_red_line(2024, 45)
    iid = sample_issue(week_year=2024, week_number=40)  # above red line
    since = _iso(datetime.now(timezone.utc) - ONE_HOUR)

    _insert_state_change(db, issue_id=iid, node_id=nodes[0]["id"],
                         old_state="developing", new_state="uat",
                         author_user_id=other["id"])

    with app.app_context():
        s = changes_summary.build_summary(
            current_user_id=user["id"], since=since, include_own=False,
        )
    ev = s["issues"][0]["events"][0]
    assert ev["flag_red_line"] is True
    assert s["counts"]["red_line_events"] == 1


def test_red_line_flag_does_not_fire_on_below_red_issue(app, db, sample_issue, nodes, make_user, set_red_line):
    user = make_user("viewer")
    other = make_user("other")
    set_red_line(2024, 45)
    iid = sample_issue(week_year=2024, week_number=50)  # below red line
    since = _iso(datetime.now(timezone.utc) - ONE_HOUR)

    _insert_state_change(db, issue_id=iid, node_id=nodes[0]["id"],
                         old_state="developing", new_state="uat",
                         author_user_id=other["id"])

    with app.app_context():
        s = changes_summary.build_summary(
            current_user_id=user["id"], since=since, include_own=False,
        )
    ev = s["issues"][0]["events"][0]
    assert ev["flag_red_line"] is False


def test_regression_flag_done_to_uat(app, db, sample_issue, nodes, make_user):
    user = make_user("viewer")
    other = make_user("other")
    iid = sample_issue()
    since = _iso(datetime.now(timezone.utc) - ONE_HOUR)

    _insert_state_change(db, issue_id=iid, node_id=nodes[0]["id"],
                         old_state="done", new_state="uat",
                         author_user_id=other["id"])

    with app.app_context():
        s = changes_summary.build_summary(
            current_user_id=user["id"], since=since, include_own=False,
        )
    ev = s["issues"][0]["events"][0]
    assert ev["flag_regression"] is True
    assert ev["progression"] == "regression"


def test_progression_does_not_flag_regression(app, db, sample_issue, nodes, make_user):
    user = make_user("viewer")
    other = make_user("other")
    iid = sample_issue()
    since = _iso(datetime.now(timezone.utc) - ONE_HOUR)

    _insert_state_change(db, issue_id=iid, node_id=nodes[0]["id"],
                         old_state="developing", new_state="uat",
                         author_user_id=other["id"])

    with app.app_context():
        s = changes_summary.build_summary(
            current_user_id=user["id"], since=since, include_own=False,
        )
    ev = s["issues"][0]["events"][0]
    assert ev["flag_regression"] is False
    assert ev["progression"] == "progression"


def test_check_in_delay_flag(app, db, sample_issue, nodes, make_user):
    user = make_user("viewer")
    other = make_user("other")
    iid = sample_issue()
    since = _iso(datetime.now(timezone.utc) - ONE_HOUR)

    _insert_state_change(db, issue_id=iid, node_id=nodes[0]["id"],
                         old_state="uat", new_state="uat",
                         old_check_in="2026-04-20", new_check_in="2026-04-30",
                         author_user_id=other["id"])

    with app.app_context():
        s = changes_summary.build_summary(
            current_user_id=user["id"], since=since, include_own=False,
        )
    ev = s["issues"][0]["events"][0]
    assert ev["flag_delay"] is True
    assert ev["check_in_delta_days"] == 10


def test_check_in_earlier_does_not_flag_delay(app, db, sample_issue, nodes, make_user):
    user = make_user("viewer")
    other = make_user("other")
    iid = sample_issue()
    since = _iso(datetime.now(timezone.utc) - ONE_HOUR)

    _insert_state_change(db, issue_id=iid, node_id=nodes[0]["id"],
                         old_state="uat", new_state="uat",
                         old_check_in="2026-04-30", new_check_in="2026-04-20",
                         author_user_id=other["id"])

    with app.app_context():
        s = changes_summary.build_summary(
            current_user_id=user["id"], since=since, include_own=False,
        )
    ev = s["issues"][0]["events"][0]
    assert ev["flag_delay"] is False


# ─── include_own ──────────────────────────────────────────────────────

def test_exclude_own_drops_user_authored_events(app, db, old_issue, nodes, make_user):
    user = make_user("viewer")
    iid = old_issue()
    since = _iso(datetime.now(timezone.utc) - ONE_HOUR)

    # Event authored by the viewing user
    _insert_state_change(db, issue_id=iid, node_id=nodes[0]["id"],
                         old_state="developing", new_state="uat",
                         author_user_id=user["id"])

    with app.app_context():
        s = changes_summary.build_summary(
            current_user_id=user["id"], since=since, include_own=False,
        )
    # include_own=False (default) → event dropped
    assert s["counts"]["total_events"] == 0

    # Now with include_own=True → event included
    with app.app_context():
        s2 = changes_summary.build_summary(
            current_user_id=user["id"], since=since, include_own=True,
        )
    assert s2["counts"]["total_events"] == 1


# ─── filter_node_id ───────────────────────────────────────────────────

def test_node_filter_shows_only_target_node_cells(app, db, sample_issue, nodes, make_user):
    user = make_user("viewer")
    other = make_user("other")
    iid = sample_issue()
    since = _iso(datetime.now(timezone.utc) - ONE_HOUR)

    # Two state changes on DIFFERENT nodes
    target_nid = nodes[0]["id"]
    other_nid = nodes[1]["id"]
    _insert_state_change(db, issue_id=iid, node_id=target_nid,
                         old_state="developing", new_state="uat",
                         author_user_id=other["id"])
    _insert_state_change(db, issue_id=iid, node_id=other_nid,
                         old_state="developing", new_state="done",
                         author_user_id=other["id"])

    with app.app_context():
        s = changes_summary.build_summary(
            current_user_id=user["id"], since=since, include_own=False,
            filter_node_id=target_nid,
        )
    events = s["issues"][0]["events"] if s["issues"] else []
    assert len(events) == 1
    assert events[0]["node_id"] == target_nid


def test_node_filter_drops_field_changes(app, db, sample_issue, nodes, make_user):
    """Field changes are issue-level, not node-specific. A node filter must
    not surface them — otherwise user sees 'JIRA changed' while filtering
    by A10, which is confusing."""
    user = make_user("viewer")
    other = make_user("other")
    iid = sample_issue()
    since = _iso(datetime.now(timezone.utc) - ONE_HOUR)

    _insert_field_change(db, issue_id=iid, field_name="jira_ticket",
                         old_value=None, new_value="JIRA-1",
                         author_user_id=other["id"])

    with app.app_context():
        s = changes_summary.build_summary(
            current_user_id=user["id"], since=since, include_own=False,
            filter_node_id=nodes[0]["id"],
        )
    assert s["counts"]["total_events"] == 0
    assert s["issues"] == []


def test_node_filter_drops_new_issue_and_closed(app, db, sample_issue, nodes, make_user):
    """Same rationale — not node-specific."""
    user = make_user("viewer")
    other = make_user("other")
    since = _iso(datetime.now(timezone.utc) - ONE_HOUR)
    later = _iso(datetime.now(timezone.utc))
    iid = sample_issue()
    db.execute(
        "UPDATE issues SET created_at=?, created_by_user_id=? WHERE id=?",
        (later, other["id"], iid),
    )
    db.commit()

    with app.app_context():
        s = changes_summary.build_summary(
            current_user_id=user["id"], since=since, include_own=False,
            filter_node_id=nodes[0]["id"],
        )
    assert s["counts"]["new_issues"] == 0
    assert s["counts"]["closed_issues"] == 0


# ─── since=None / empty DB ────────────────────────────────────────────

def test_empty_db_returns_zero_counts(app, db, make_user):
    user = make_user("viewer")
    since = _iso(datetime.now(timezone.utc) - ONE_HOUR)
    with app.app_context():
        s = changes_summary.build_summary(
            current_user_id=user["id"], since=since, include_own=False,
        )
    assert s["counts"]["total_events"] == 0
    assert s["counts"]["total_issues"] == 0
    assert s["issues"] == []


def test_since_none_returns_nothing(app, db, sample_issue, nodes, make_user):
    """New user with no last_viewed_at → since is None → nothing to show."""
    user = make_user("viewer")
    other = make_user("other")
    iid = sample_issue()
    _insert_state_change(db, issue_id=iid, node_id=nodes[0]["id"],
                         old_state=None, new_state="uat",
                         author_user_id=other["id"])
    with app.app_context():
        s = changes_summary.build_summary(
            current_user_id=user["id"], since=None, include_own=False,
        )
    assert s["counts"]["total_events"] == 0


# ─── count_important counts ALL authors (including current user) ──────

def test_count_important_includes_own_events(app, db, old_issue, nodes, make_user):
    """The navbar badge must agree with /changes default. Since /changes
    now defaults to showing everything, count_important must also count
    events authored by the viewing user."""
    user = make_user("viewer")
    set_red_line_year, set_red_line_week = 2024, 45  # below-red issue
    iid = old_issue(week_year=2024, week_number=40)  # above red line
    db.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)",
               ("red_line_week_year", str(set_red_line_year)))
    db.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)",
               ("red_line_week_number", str(set_red_line_week)))
    db.commit()
    since = _iso(datetime.now(timezone.utc) - ONE_HOUR)

    # Author the event as `user` themselves — this would be hidden in
    # the old "exclude own" badge, but NOW must count.
    _insert_state_change(db, issue_id=iid, node_id=nodes[0]["id"],
                         old_state="developing", new_state="uat",
                         author_user_id=user["id"])

    with app.app_context():
        n = changes_summary.count_important(since=since)
    # Above red line + state changed → 1 important event
    assert n == 1


def test_count_important_zero_when_no_events(app, db, make_user):
    user = make_user("viewer")
    since = _iso(datetime.now(timezone.utc) - ONE_HOUR)
    with app.app_context():
        assert changes_summary.count_important(since=since) == 0


def test_count_important_ignores_non_important_state_changes(app, db, old_issue, nodes, make_user):
    """Normal progression on below-red issue shouldn't count."""
    user = make_user("viewer")
    # No red line set → nothing is above red line → state change is plain.
    iid = old_issue()
    since = _iso(datetime.now(timezone.utc) - ONE_HOUR)
    _insert_state_change(db, issue_id=iid, node_id=nodes[0]["id"],
                         old_state="developing", new_state="uat",
                         author_user_id=user["id"])
    with app.app_context():
        assert changes_summary.count_important(since=since) == 0


# ─── /changes route default behavior ──────────────────────────────────

def test_changes_route_default_includes_own(app, client, db, make_user, nodes, old_issue):
    """GET /changes (no query string) must default to include_own=True."""
    user = make_user("viewer")
    iid = old_issue()
    # Set user's last_viewed_at so `since` is defined
    db.execute("UPDATE users SET last_viewed_at = ? WHERE id = ?",
               (_iso(datetime.now(timezone.utc) - ONE_HOUR), user["id"]))
    db.commit()
    # User made their own state change
    _insert_state_change(db, issue_id=iid, node_id=nodes[0]["id"],
                         old_state="developing", new_state="uat",
                         author_user_id=user["id"])
    # Log in as user
    with client.session_transaction() as s:
        s["user_id"] = user["id"]
        s.permanent = True

    r = client.get("/changes")
    assert r.status_code == 200
    # The event should be visible on the page (own operation included by default)
    body = r.data.decode("utf-8", errors="replace")
    assert "chg-event-item" in body


def test_changes_route_include_own_0_hides_own(app, client, db, make_user, nodes, old_issue):
    """Explicit ?include_own=0 → hide own events."""
    user = make_user("viewer")
    iid = old_issue()
    db.execute("UPDATE users SET last_viewed_at = ? WHERE id = ?",
               (_iso(datetime.now(timezone.utc) - ONE_HOUR), user["id"]))
    db.commit()
    _insert_state_change(db, issue_id=iid, node_id=nodes[0]["id"],
                         old_state="developing", new_state="uat",
                         author_user_id=user["id"])
    with client.session_transaction() as s:
        s["user_id"] = user["id"]
        s.permanent = True

    r = client.get("/changes?include_own=0")
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="replace")
    # No own events should appear → no issue cards
    assert "chg-event-item" not in body
