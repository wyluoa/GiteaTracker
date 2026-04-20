"""Reset every user's last_viewed_at to the migration time.

Effect: immediately after migration, nobody sees any pre-migration change as
"new" (no yellow highlight). Going forward, only updates made after the
migration time will trigger highlights until the user marks-as-read again.

This is applied once (tied to this migration version), so restoring an older
DB and re-running migrations will re-apply this baseline at that moment. If
that is not desired after a restore, remove the schema_version row for '002'
and the effect will be re-applied on next migrate — or leave it alone and let
users click '標記已讀' to adjust.
"""
from datetime import datetime, timezone

SCHEMA_VERSION = "002"
DESCRIPTION = "users.last_viewed_at = migrate time (clean-slate mark-as-read for everyone)"


def up(conn):
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE users SET last_viewed_at = ?", (now,))
