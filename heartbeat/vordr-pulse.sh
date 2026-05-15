#!/usr/bin/env bash
# Vörðr — Post-turn continuation nudge.
# Runs every 5 minutes. If work remains, nudges Runa to continue.
set -euo pipefail

VORDR="/home/pi/verdandi/heartbeat/vordr.py"
LOG="/home/pi/.hermes/logs/vordr.log"
mkdir -p "$(dirname "$LOG")"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Vörðr pulse" >> "$LOG"
python3 "$VORDR" --quiet >> "$LOG" 2>&1
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Vörðr complete" >> "$LOG"