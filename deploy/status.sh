#!/bin/bash
# Gitea Tracker — check service status (no sudo required)
# Usage: ./deploy/status.sh

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="${APP_DIR}/logs/app.pid"

if [ ! -f "${PID_FILE}" ]; then
    echo "Gitea Tracker is NOT running (no PID file)"
    exit 1
fi

PID=$(cat "${PID_FILE}")

if kill -0 "${PID}" 2>/dev/null; then
    echo "Gitea Tracker is running (PID ${PID})"
    # Show uptime info
    ps -o pid,etime,rss -p "${PID}" 2>/dev/null | tail -1 | \
        awk '{printf "  PID: %s | Uptime: %s | Memory: %.1f MB\n", $1, $2, $3/1024}'
    exit 0
else
    echo "Gitea Tracker is NOT running (stale PID file, was PID ${PID})"
    rm -f "${PID_FILE}"
    exit 1
fi
