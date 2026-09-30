#!/bin/bash
# nerve_supervise.sh — Verðandi nerve hub supervisor.
# Keeps the hub alive: if the hub process exits for ANY reason (SIGKILL, OOM,
# crash), this restarts it within seconds and logs the exit code.
# Run detached:  setsid nohup nerve_supervise.sh < /dev/null >supervisor.out 2>&1 &
# Stop cleanly:  touch ~/.hermes/state/nerve_supervisor.stop  (supervisor exits
#                after stopping the hub) — or just kill the supervisor PID.
set -u
REPO="$HOME/workspace/repos/Verdandi"
HUBLOG="$HOME/workspace/verdandi_hub.log"
SUPLOG="$HOME/workspace/verdandi_supervisor.log"
PIDFILE="$HOME/.hermes/state/nerve_supervisor.pid"
STOPFILE="$HOME/.hermes/state/nerve_supervisor.stop"
BRIDGE_PIDFILE="$HOME/.hermes/state/telegram_bridge.pid"
BRIDGELOG="$HOME/workspace/verdandi_telegram_bridge.log"

mkdir -p "$HOME/.hermes/state"
echo $$ > "$PIDFILE"
echo "$(date '+%F %T') supervisor started (pid $$)" >> "$SUPLOG"

backoff=5
while true; do
    if [ -f "$STOPFILE" ]; then
        echo "$(date '+%F %T') stop file seen — stopping hub and exiting" >> "$SUPLOG"
        python3 "$REPO/nervous_system.py" stop >> "$SUPLOG" 2>&1
        if [ -f "$BRIDGE_PIDFILE" ]; then
            kill "$(cat "$BRIDGE_PIDFILE")" 2>/dev/null || true
            rm -f "$BRIDGE_PIDFILE"
            echo "$(date '+%F %T') telegram bridge stopped" >> "$SUPLOG"
        fi
        rm -f "$STOPFILE" "$PIDFILE"
        exit 0
    fi
    # --- Telegram bridge: kept alive alongside the hub. Non-destructive peek
    # (never sends offset), so the D&D game watcher stays the queue's owner.
    if [ ! -f "$BRIDGE_PIDFILE" ] || ! kill -0 "$(cat "$BRIDGE_PIDFILE" 2>/dev/null)" 2>/dev/null; then
        echo "$(date '+%F %T') telegram bridge not running — starting" >> "$SUPLOG"
        python3 -u "$REPO/telegram_bridge.py" >> "$BRIDGELOG" 2>&1 < /dev/null &
        echo $! > "$BRIDGE_PIDFILE"
    fi
    # If a healthy hub is already up (e.g. started by hand), just watch it.
    if python3 "$REPO/nervous_system.py" healthcheck >/dev/null 2>&1; then
        sleep 15
        backoff=5
        continue
    fi
    echo "$(date '+%F %T') hub not healthy — starting (backoff ${backoff}s)" >> "$SUPLOG"
    sleep "$backoff"
    cd "$REPO" || exit 1
    # Foreground child: `wait` below reaps it and reports the true exit code.
    python3 -u nervous_system.py serve >> "$HUBLOG" 2>&1 < /dev/null &
    HUBPID=$!
    wait "$HUBPID"
    code=$?
    echo "$(date '+%F %T') hub pid $HUBPID exited code=$code (137=SIGKILL/OOM, 143=SIGTERM)" >> "$SUPLOG"
    # Exponential backoff on rapid crash loops, cap 5 min
    if [ "$backoff" -lt 300 ]; then backoff=$(( backoff * 2 )); fi
done
