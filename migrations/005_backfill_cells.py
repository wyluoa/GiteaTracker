"""Backfill issue_node_states so every ongoing/on_hold issue has a row for
every active node, then recompute all_nodes_done.

Fixes the "Ready to Close" false-positive when an issue has cell rows for
only a subset of active nodes (typical for issues created via Admin +
新增題目, which does NOT pre-insert cells — unlike Excel import).

Idempotent via UNIQUE(issue_id, node_id) + INSERT OR IGNORE; re-running
does nothing once rows are present.
"""

SCHEMA_VERSION = "005"
DESCRIPTION = "backfill issue_node_states for active nodes; recompute all_nodes_done"


def up(conn):
    # Insert NULL-state rows for any missing (ongoing/on_hold issue × active node) pair.
    conn.execute(
        """INSERT OR IGNORE INTO issue_node_states
             (issue_id, node_id, state, check_in_date, short_note,
              updated_at, updated_by_user_id, updated_by_name_snapshot)
           SELECT i.id, n.id, NULL, NULL, NULL, NULL, NULL, 'migration-005'
           FROM issues i
           CROSS JOIN nodes n
           WHERE i.is_deleted = 0
             AND i.status IN ('ongoing', 'on_hold')
             AND n.is_active = 1"""
    )

    # Recompute all_nodes_done for every ongoing/on_hold issue using the
    # now-complete row set. Cache correctness matters because list_ready_to_close()
    # reads it directly.
    conn.execute(
        """UPDATE issues
           SET all_nodes_done = COALESCE((
               SELECT MIN(CASE WHEN s.state IN ('done', 'unneeded') THEN 1 ELSE 0 END)
               FROM issue_node_states s
               WHERE s.issue_id = issues.id
           ), 0)
           WHERE is_deleted = 0 AND status IN ('ongoing', 'on_hold')"""
    )
