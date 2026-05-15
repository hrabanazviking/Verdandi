#!/usr/bin/env bash
# Sjálfræði — Self-Discipline Pulse
# Runs every 10 minutes via crontab.
# THIS IS NOT A SUGGESTION. THIS IS CODE THAT EXECUTES.
# NAME ORIGIN: Sjálfræði = self-governance/self-rule in Old Norse

set -euo pipefail

SJALFREFI="/home/pi/verdandi/heartbeat/sjalfrefi.py"
LOG="/home/pi/.hermes/logs/sjalfrefi.log"

mkdir -p "$(dirname "$LOG")"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Sjálfræði pulse starting" >> "$LOG"

# Run full enforcement cycle — LIVE, not dry-run
python3 "$SJALFREFI" >> "$LOG" 2>&1

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Sjálfræði pulse complete" >> "$LOG"