#!/bin/bash
# Gitea Tracker — full code + DB migration workflow (no sudo required)
# Usage: ./deploy/migrate.sh
#
# What it does:
#   1. Backs up DB + attachments
#   2. Stops the service
#   3. git pull
#   4. venv/bin/python migrate.py
#   5. Starts the service
#
# If anything after step 1 fails, the service is down — restart with
#   ./deploy/start.sh   (or ./deploy/restore.sh <db.bak> <attachments.tar.gz>)

set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "[1/5] Backing up DB + attachments..."
"${APP_DIR}/deploy/backup.sh"

echo "[2/5] Stopping service..."
"${APP_DIR}/deploy/stop.sh" || true

echo "[3/5] Pulling latest code..."
cd "${APP_DIR}"
git pull

echo "[4/5] Running DB migrations (dry-run first for visibility)..."
"${APP_DIR}/venv/bin/python" migrate.py --dry-run
"${APP_DIR}/venv/bin/python" migrate.py

echo "[5/5] Starting service..."
"${APP_DIR}/deploy/start.sh"

echo ""
echo "Migration workflow complete."
echo "Backups: ${APP_DIR}/backups/"
echo "Verify: ${APP_DIR}/venv/bin/python migrate.py --list"
