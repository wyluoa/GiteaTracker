"""
State transition role gates:

  Done     → super_user only
  Unneeded → super_user OR manager
  others   → any editor with node permission

Mandatory note: any real state change must include an update note (body).
"""
import pytest

from app.routes.issues import _state_change_allowed


# ─── Unit-level: the gate helper ──────────────────────────────────────

@pytest.mark.parametrize("state,role,expected", [
    # Done — super only
    ("done",       "super",   True),
    ("done",       "manager", False),
    ("done",       "editor",  False),
    # Unneeded — super or manager
    ("unneeded",   "super",   True),
    ("unneeded",   "manager", True),
    ("unneeded",   "editor",  False),
    # UAT / Dev / TBD / UAT done — anyone
    ("uat",        "editor",  True),
    ("developing", "editor",  True),
    ("tbd",        "editor",  True),
    ("uat_done",   "editor",  True),
    ("uat_done",   "manager", True),
    ("uat_done",   "super",   True),
    # Empty state also fine for anyone
    (None,         "editor",  True),
])
def test_state_gate_matrix(state, role, expected):
    user = {
        "is_super_user": role == "super",
        "is_manager":    role == "manager",
    }
    allowed, _reason = _state_change_allowed(user, state)
    assert allowed is expected


# ─── Integration: POST /issues/<id>/cell/<nid> round-trip ──────────────

def _post_cell(client, issue_id, node_id, **form):
    return client.post(f"/issues/{issue_id}/cell/{node_id}", data=form,
                       follow_redirects=False)


def test_editor_can_change_to_uat(client, login_as, editor_user, sample_issue, nodes):
    iid = sample_issue()
    nid = nodes[0]["id"]
    login_as(editor_user)

    r = _post_cell(client, iid, nid, state="uat", body="move to UAT")
    assert r.status_code == 200

    # timeline_entry recorded
    from app.db import get_db
    with client.application.app_context():
        db = get_db()
        entries = db.execute(
            "SELECT * FROM timeline_entries WHERE issue_id = ? AND entry_type='state_change'",
            (iid,),
        ).fetchall()
    assert len(entries) == 1
    assert entries[0]["new_state"] == "uat"
    assert entries[0]["old_state"] is None
    assert entries[0]["body"] == "move to UAT"


def test_editor_cannot_set_done(client, login_as, editor_user, sample_issue, nodes):
    iid = sample_issue()
    nid = nodes[0]["id"]
    login_as(editor_user)

    r = _post_cell(client, iid, nid, state="done", body="done-attempt")
    # Route flashes error + re-renders side panel with 200 — the cell row
    # must NOT have been written.
    from app.db import get_db
    with client.application.app_context():
        db = get_db()
        cell = db.execute(
            "SELECT * FROM issue_node_states WHERE issue_id=? AND node_id=?",
            (iid, nid),
        ).fetchone()
    assert cell is None, "editor should not have been able to set done"


def test_editor_cannot_set_unneeded(client, login_as, editor_user, sample_issue, nodes):
    iid = sample_issue()
    nid = nodes[0]["id"]
    login_as(editor_user)

    _post_cell(client, iid, nid, state="unneeded", body="skip")
    from app.db import get_db
    with client.application.app_context():
        db = get_db()
        cell = db.execute(
            "SELECT * FROM issue_node_states WHERE issue_id=? AND node_id=?",
            (iid, nid),
        ).fetchone()
    assert cell is None, "editor should not have been able to set unneeded"


def test_manager_can_set_unneeded_but_not_done(client, login_as, manager_user, sample_issue, nodes, db):
    iid = sample_issue()
    nid = nodes[0]["id"]
    # Put the manager in a group with access to this node, otherwise
    # the @can_edit_node decorator blocks before the state gate runs.
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    cur = db.execute(
        "INSERT INTO groups (name, description, is_active, created_at) VALUES ('m', '', 1, ?)",
        (now,),
    )
    gid = cur.lastrowid
    db.execute("INSERT INTO user_groups VALUES (?, ?)", (manager_user["id"], gid))
    db.execute("INSERT INTO group_nodes VALUES (?, ?)", (gid, nid))
    db.commit()

    login_as(manager_user)

    # Unneeded — allowed
    r = _post_cell(client, iid, nid, state="unneeded", body="not applicable")
    assert r.status_code == 200
    from app.db import get_db
    with client.application.app_context():
        d2 = get_db()
        cell = d2.execute(
            "SELECT state FROM issue_node_states WHERE issue_id=? AND node_id=?",
            (iid, nid),
        ).fetchone()
    assert cell["state"] == "unneeded"

    # Done — blocked
    r = _post_cell(client, iid, nid, state="done", body="try done")
    with client.application.app_context():
        d2 = get_db()
        cell = d2.execute(
            "SELECT state FROM issue_node_states WHERE issue_id=? AND node_id=?",
            (iid, nid),
        ).fetchone()
    assert cell["state"] == "unneeded", "manager shouldn't have flipped to done"


def test_super_user_can_set_done(client, login_as, super_user, sample_issue, nodes):
    iid = sample_issue()
    nid = nodes[0]["id"]
    login_as(super_user)

    r = _post_cell(client, iid, nid, state="done", body="shipped")
    assert r.status_code == 200

    from app.db import get_db
    with client.application.app_context():
        db = get_db()
        cell = db.execute(
            "SELECT state FROM issue_node_states WHERE issue_id=? AND node_id=?",
            (iid, nid),
        ).fetchone()
    assert cell["state"] == "done"


def test_state_change_without_note_is_rejected(client, login_as, editor_user, sample_issue, nodes):
    """State change requires a non-empty body — the route must not write
    the cell or a timeline entry if body is missing."""
    iid = sample_issue()
    nid = nodes[0]["id"]
    login_as(editor_user)

    r = _post_cell(client, iid, nid, state="uat", body="")  # empty note
    assert r.status_code == 200

    from app.db import get_db
    with client.application.app_context():
        db = get_db()
        cell = db.execute(
            "SELECT * FROM issue_node_states WHERE issue_id=? AND node_id=?",
            (iid, nid),
        ).fetchone()
        entries = db.execute(
            "SELECT * FROM timeline_entries WHERE issue_id=? AND entry_type='state_change'",
            (iid,),
        ).fetchall()
    assert cell is None
    assert entries == []


def test_unchanged_cell_does_not_require_note(client, login_as, editor_user, sample_issue, nodes, db):
    """If the user submits the same state they already had (no cell change),
    the mandatory-note rule doesn't fire — otherwise they couldn't just
    open/close a side panel."""
    iid = sample_issue()
    nid = nodes[0]["id"]
    # Seed the cell with an existing state
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """INSERT INTO issue_node_states
           (issue_id, node_id, state, updated_at, updated_by_user_id, updated_by_name_snapshot)
           VALUES (?, ?, 'uat', ?, ?, 'seed')""",
        (iid, nid, now, editor_user["id"]),
    )
    db.commit()

    login_as(editor_user)
    # Re-submit 'uat' with empty body — nothing changed, should be fine.
    r = _post_cell(client, iid, nid, state="uat", body="")
    assert r.status_code == 200
