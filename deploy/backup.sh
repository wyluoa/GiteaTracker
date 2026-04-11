#!/bin/bash
# Gitea Tracker backup script
# Usage: ./backup.sh [backup_dir]
#
# Backs up the SQLite database and attachments directory.
# Recommended: run via cron daily, e.g.
#   0 2 * * * /opt/gitea-tracker/deploy/backup.sh /opt/gitea-tracker/backups

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/gitea-tracker}"
BACKUP_DIR="${1:-${APP_DIR}/backups}"
DATE=$(date +%Y%m%d_%H%M%S)
DB_PATH="${APP_DIR}/data/gitea_tracker.db"
ATT_DIR="${APP_DIR}/data/attachments"

mkdir -p "${BACKUP_DIR}"

# SQLite online backup (safe even while app is running)
sqlite3 "${DB_PATH}" ".backup '${BACKUP_DIR}/gitea_tracker_${DATE}.db'"

# Compress attachments
if [ -d "${ATT_DIR}" ] && [ "$(ls -A ${ATT_DIR} 2>/dev/null)" ]; then
    tar czf "${BACKUP_DIR}/attachments_${DATE}.tar.gz" -C "${APP_DIR}/data" attachments
fi

# Keep only last 30 days of backups
find "${BACKUP_DIR}" -name "gitea_tracker_*.db" -mtime +30 -delete 2>/dev/null || true
find "${BACKUP_DIR}" -name "attachments_*.tar.gz" -mtime +30 -delete 2>/dev/null || true

echo "[$(date)] Backup completed: ${BACKUP_DIR}/gitea_tracker_${DATE}.db"
