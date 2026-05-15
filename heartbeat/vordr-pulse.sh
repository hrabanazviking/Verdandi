#!/usr/bin/env bash
# Vörðr — Post-turn continuation nudge.
# Runs every 5 minutes. If work remains, nudges Runa to continue.
set -euo pipefail

# Ensure hermes CLI is on PATH (crontab has minimal PATH)
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

VORDR="$HOME/verdandi/heartbeat/vordr.py"
LOG="$HOME/.hermes/logs/vordr.log"
mkdir -p "$(dirname "$LOG")"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Vörðr pulse" >> "$LOG"
python3 "$VORDR" --quiet >> "$LOG" 2>&1
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Vörðr complete" >> "$LOG"