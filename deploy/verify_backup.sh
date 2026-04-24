#!/bin/bash
# Verify that the most recent backup can actually be restored and queried.
#
# "Your backup is only as good as your last verified restore."
# This script runs the latest DB backup against a tmp dir, opens it,
# runs a sanity SELECT, and reports success/failure. Safe to cron weekly.
#
# Usage:  ./deploy/verify_backup.sh
# Exits 0 on success, non-zero on any problem (so cron mail fires).

set -euo pipefail
export PYTHONIOENCODING=utf-8   # Prevent latin-1 crashes under cron/POSIX locale.

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${APP_DIR}/backups"
PYTHON="${APP_DIR}/venv/bin/python"

if [ ! -d "${BACKUP_DIR}" ]; then
    echo "FAIL: no backups/ directory" >&2
    exit 1
fi

LATEST="$(find "${BACKUP_DIR}" -maxdepth 1 -name 'gitea_tracker_*.db' \
          -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)"
if [ -z "${LATEST}" ]; then
    echo "FAIL: no gitea_tracker_*.db backups present" >&2
    exit 2
fi

TMPFILE="$(mktemp --suffix=.db)"
trap 'rm -f "${TMPFILE}"' EXIT

cp "${LATEST}" "${TMPFILE}"

"${PYTHON}" - <<PY
import sqlite3, sys
conn = sqlite3.connect("${TMPFILE}")
try:
    t = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )}
    required = {"issues", "users", "nodes", "timeline_entries", "schema_version"}
    missing = required - t
    if missing:
        print(f"FAIL: missing tables: {missing}", file=sys.stderr)
        sys.exit(3)
    n_issues = conn.execute("SELECT COUNT(*) FROM issues").fetchone()[0]
    n_users  = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print(f"OK: ${LATEST} restored & queried - issues={n_issues}, users={n_users}")
finally:
    conn.close()
PY
