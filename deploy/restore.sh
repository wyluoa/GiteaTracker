#!/bin/bash
# Gitea Tracker restore script
# Usage: ./restore.sh <db_backup_file> [attachments_tar_gz]
#
# Stops the service, restores DB (and optionally attachments), restarts.

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/gitea-tracker}"
DB_PATH="${APP_DIR}/data/gitea_tracker.db"

if [ $# -lt 1 ]; then
    echo "Usage: $0 <db_backup_file> [attachments_tar_gz]"
    echo "Example: $0 backups/gitea_tracker_20260411.db backups/attachments_20260411.tar.gz"
    exit 1
fi

DB_BACKUP="$1"
ATT_BACKUP="${2:-}"

echo "Stopping gitea-tracker service..."
sudo systemctl stop gitea-tracker || true

echo "Restoring database from ${DB_BACKUP}..."
cp "${DB_BACKUP}" "${DB_PATH}"

if [ -n "${ATT_BACKUP}" ] && [ -f "${ATT_BACKUP}" ]; then
    echo "Restoring attachments from ${ATT_BACKUP}..."
    rm -rf "${APP_DIR}/data/attachments"
    tar xzf "${ATT_BACKUP}" -C "${APP_DIR}/data"
fi

echo "Starting gitea-tracker service..."
sudo systemctl start gitea-tracker

echo "Restore completed."
