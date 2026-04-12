#!/bin/bash
# Gitea Tracker — stop service (no sudo required)
# Usage: ./deploy/stop.sh

set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="${APP_DIR}/logs/app.pid"

if [ ! -f "${PID_FILE}" ]; then
    echo "PID file not found. Gitea Tracker may not be running."
    exit 0
fi

PID=$(cat "${PID_FILE}")

if kill -0 "${PID}" 2>/dev/null; then
    kill "${PID}"
    echo "Gitea Tracker stopped (PID ${PID})"
else
    echo "Process ${PID} is not running (stale PID file)."
fi

rm -f "${PID_FILE}"
