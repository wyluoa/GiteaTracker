#!/bin/bash
# PreToolUse hook — blocks Write/Edit tools targeting data/attachments/**.
#
# Rationale: data/attachments/ holds user-uploaded files whose paths are
# referenced by attachments.stored_path in the DB. Editing or overwriting
# them corrupts the linkage. Moves/cleanups must be done manually with
# backup, not through Claude's tool calls.
#
# Input: JSON on stdin (PreToolUse payload).
# Exit 0 = allow, exit 2 = block with stderr shown to Claude + user.
set -euo pipefail

input="$(cat)"

# Extract the target file_path from tool_input. Handles Write / Edit.
file_path="$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get("tool_input", {}).get("file_path", ""))
except Exception:
    print("")
' 2>/dev/null || printf "")"

if [ -z "$file_path" ]; then
    exit 0
fi

case "$file_path" in
    */data/attachments/*|data/attachments/*)
        cat >&2 <<'EOF'
Blocked: data/attachments/ contains user-uploaded files linked from the DB
(attachments.stored_path). Claude must not Write/Edit these paths.

If you genuinely need to move / delete / rename attachments:
  1. Take a backup (./deploy/backup.sh)
  2. Do it manually from a shell, updating the DB rows in lockstep
  3. Do NOT put this in a migration (migrations never touch attachment files)
EOF
        exit 2
        ;;
esac

exit 0
