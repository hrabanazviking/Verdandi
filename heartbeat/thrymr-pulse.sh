#!/usr/bin/env bash
# Þrymr Enforcement Pulse — runs every 15 minutes via crontab
# This is the ticking heart of the enforcement system.
# It NEVER stops. It NEVER gives up. It enforces discipline.

set -euo pipefail

THRYMR="/home/pi/verdandi/heartbeat/thrymr.py"
LOG="/home/pi/.hermes/logs/thrymr.log"

mkdir -p "$(dirname "$LOG")"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Þrymr pulse starting" >> "$LOG"

# Run enforcement cycle — LIVE, not dry-run
python3 "$THRYMR" >> "$LOG" 2>&1

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Þrymr pulse complete" >> "$LOG"