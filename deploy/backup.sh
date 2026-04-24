#!/bin/bash
# Gitea Tracker backup script (no sudo required)
#
# Usage:  ./deploy/backup.sh [backup_dir]
#
# Backs up the SQLite database + attachments directory, and (optionally)
# syncs the result to an off-site destination.
#
# Off-site sync:
#   Set env var  GITEA_TRACKER_OFFSITE=user@host:/path/backups
#   (or a local dir like /mnt/nas/gitea_tracker_backups)
#   and the script will rsync the freshly-created files there too.
#
# Crontab example (daily 2 AM, then weekly off-site copy):
#   0 2 * * *  GITEA_TRACKER_OFFSITE="user@nas:/backups/giteatr" ~/GiteaTracker/deploy/backup.sh
#
# IMPORTANT: runs purely in Python — does NOT require `sqlite3` CLI
#            (which is not present on some corporate Linux images).
#
# ENCODING: always export PYTHONIOENCODING=utf-8 before any Python heredoc
#           and keep printed strings ASCII-only. Cron / corporate locales
#           often default to C / POSIX / latin-1 and will crash Python on
#           a bare Unicode character (e.g. "→"). See deploy/MIGRATION_SOP.md.

set -euo pipefail
export PYTHONIOENCODING=utf-8

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${1:-${APP_DIR}/backups}"
DATE=$(date +%Y%m%d_%H%M%S)
DB_PATH="${APP_DIR}/data/gitea_tracker.db"
ATT_DIR="${APP_DIR}/data/attachments"
PYTHON="${APP_DIR}/venv/bin/python"

mkdir -p "${BACKUP_DIR}"

DB_BACKUP="${BACKUP_DIR}/gitea_tracker_${DATE}.db"
ATT_BACKUP="${BACKUP_DIR}/attachments_${DATE}.tar.gz"

# ── 1. SQLite online backup via Python (safe while app is running) ──
# Uses sqlite3.Connection.backup(), which is the same online-backup
# mechanism as the `sqlite3 .backup` CLI command but without needing
# the CLI installed.
"${PYTHON}" - <<PY
import sqlite3, sys
src_path = "${DB_PATH}"
dst_path = "${DB_BACKUP}"
src = sqlite3.connect(src_path)
dst = sqlite3.connect(dst_path)
try:
    src.backup(dst)
finally:
    dst.close(); src.close()
print(f"DB backed up -> {dst_path}")
PY

# ── 2. Attachments tarball ──
if [ -d "${ATT_DIR}" ] && [ "$(ls -A "${ATT_DIR}" 2>/dev/null)" ]; then
    tar czf "${ATT_BACKUP}" -C "${APP_DIR}/data" attachments
    echo "Attachments archived -> ${ATT_BACKUP}"
fi

# ── 3. Retention: keep last 30 days locally ──
find "${BACKUP_DIR}" -name "gitea_tracker_*.db" -mtime +30 -delete 2>/dev/null || true
find "${BACKUP_DIR}" -name "attachments_*.tar.gz" -mtime +30 -delete 2>/dev/null || true

# ── 4. Optional off-site copy ──
# The local backups are on the SAME machine as the live DB. If the machine
# dies, the backups die with it. Set GITEA_TRACKER_OFFSITE to push a copy
# elsewhere (NAS, another server, network share).
if [ -n "${GITEA_TRACKER_OFFSITE:-}" ]; then
    if command -v rsync >/dev/null 2>&1; then
        echo "Off-site sync -> ${GITEA_TRACKER_OFFSITE}"
        rsync -aq --partial "${DB_BACKUP}" "${GITEA_TRACKER_OFFSITE}/" \
            || echo "  WARN: rsync DB failed (continuing)" >&2
        if [ -f "${ATT_BACKUP}" ]; then
            rsync -aq --partial "${ATT_BACKUP}" "${GITEA_TRACKER_OFFSITE}/" \
                || echo "  WARN: rsync attachments failed (continuing)" >&2
        fi
    else
        echo "  WARN: GITEA_TRACKER_OFFSITE set but rsync not found — skipping off-site copy" >&2
    fi
fi

echo "[$(date)] Backup completed: ${DB_BACKUP}"
