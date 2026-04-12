#!/bin/bash
# Gitea Tracker — start service (no sudo required)
# Usage: ./deploy/start.sh

set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${APP_DIR}/logs"
PID_FILE="${APP_DIR}/logs/app.pid"

mkdir -p "${LOG_DIR}"

# Check if already running
if [ -f "${PID_FILE}" ]; then
    OLD_PID=$(cat "${PID_FILE}")
    if kill -0 "${OLD_PID}" 2>/dev/null; then
        echo "Gitea Tracker is already running (PID ${OLD_PID})"
        echo "Use deploy/stop.sh to stop it first."
        exit 1
    else
        rm -f "${PID_FILE}"
    fi
fi

# Start in background with nohup
cd "${APP_DIR}"
nohup "${APP_DIR}/venv/bin/python" main.py >> "${LOG_DIR}/app.log" 2>&1 &
echo $! > "${PID_FILE}"

echo "Gitea Tracker started (PID $(cat "${PID_FILE}"))"
echo "Log: ${LOG_DIR}/app.log"
