#!/bin/bash
# PreToolUse hook — blocks `migrate.py` (mutating form) when backups/ has no
# recent DB backup.
#
# Rationale: migrations can alter schema / mutate data. A stale or missing
# backup means there's no safe rollback. Read-only flags (--dry-run, --list)
# are allowed through.
#
# Input: JSON on stdin (PreToolUse payload with Bash tool_input.command).
# Exit 0 = allow, exit 2 = block with stderr message.
#
# Threshold: a backup within 24h (1440 min) is considered fresh.
set -euo pipefail

input="$(cat)"

cmd="$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get("tool_input", {}).get("command", ""))
except Exception:
    print("")
' 2>/dev/null || printf "")"

# Only intercept *executions* of migrate.py (interpreter + script, or ./migrate.py).
# NOT commands that merely mention the filename as an argument (git add, ls, cat).
case "$cmd" in
    *python*migrate.py*|./migrate.py*|./migrate.py) : ;;
    *) exit 0 ;;
esac

# Allow read-only flags without backup check.
case "$cmd" in
    *--dry-run*|*--list*|*--help*|*-h*) exit 0 ;;
esac

# Find project root relative to this hook script (.claude/hooks/ → ../..).
root="$(cd "$(dirname "$0")/../.." && pwd)"
backup_dir="$root/backups"

if [ ! -d "$backup_dir" ]; then
    cat >&2 <<EOF
Blocked: migrate.py is about to mutate the DB but '$backup_dir' does not exist.
Run './deploy/backup.sh' first to create a backup, then retry.
EOF
    exit 2
fi

# Look for a DB backup less than 1440 minutes (24h) old.
recent="$(find "$backup_dir" -maxdepth 1 -name 'gitea_tracker_*.db' -mmin -1440 2>/dev/null | head -1)"
if [ -z "$recent" ]; then
    cat >&2 <<EOF
Blocked: migrate.py is about to mutate the DB but no DB backup in the last 24h
was found under '$backup_dir'. Run './deploy/backup.sh' first (or use
'--dry-run' / '--list' for read-only checks).
EOF
    exit 2
fi

exit 0
