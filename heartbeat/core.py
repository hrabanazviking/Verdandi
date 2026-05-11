"""
Verðandi Heartbeat Core — The Pulse of Becoming.

The main daemon loop. Each pulse checks health, projects, memory, and schedule,
then reacts to what it finds. The state machine tracks overall system health:

  INITIALIZING → RUNNING → DEGRADED → CRITICAL → RECOVERING
                    ↑           ↑           │
                    └───────────┴───────────┘

States:
  - INITIALIZING: Starting up, first pulse not yet completed
  - RUNNING: All checks pass within thresholds
  - DEGRADED: One or more checks in warning state (but not critical)
  - CRITICAL: One or more checks exceeded critical thresholds
  - RECOVERING: Was critical/degraded, now recovering

Every pulse fires a nerve impulse to the nerve hub. Every state change
is logged, stored in Mímir (if available), and triggers appropriate
recovery actions.

This is not a monitor. This is a living system that feels its own pulse.
"""

import json
import os
import time
import random
import logging
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

from heartbeat.config import HeartbeatConfig, DEFAULTS
from heartbeat.paths import (
    get_state_dir, get_log_dir, get_pid_dir, get_socket_path,
    get_config_path, get_db_path, get_pid_path, get_log_path,
    get_platform_info, ensure_dirs,
)
from heartbeat.signals import SignalHandler, DaemonContext
from heartbeat.checks import CHECK_REGISTRY
from heartbeat.checks.base import BaseCheck, CheckResult, CheckSeverity

logger = logging.getLogger("verdandi.heartbeat")


# ─────────────────────────────────────────────────────
# State Machine — The Daemon's Consciousness Levels
# ─────────────────────────────────────────────────────

class DaemonState(Enum):
    """System health states, ordered by severity."""
    INITIALIZING = "initializing"
    RUNNING = "running"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    RECOVERING = "recovering"
    SHUTTING_DOWN = "shutting_down"


@dataclass
class HeartbeatState:
    """Full state snapshot of the daemon."""
    state: DaemonState = DaemonState.INITIALIZING
    pulse_count: int = 0
    last_pulse: str = ""
    last_healthy_pulse: str = ""
    started_at: str = ""
    checks: dict[str, CheckResult] = field(default_factory=dict)
    uptime_seconds: float = 0.0
    config_source: str = ""
    platform: str = ""

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "state": self.state.value,
            "pulse_count": self.pulse_count,
            "last_pulse": self.last_pulse,
            "last_healthy_pulse": self.last_healthy_pulse,
            "started_at": self.started_at,
            "uptime_seconds": self.uptime_seconds,
            "config_source": self.config_source,
            "platform": self.platform,
            "checks": {
                name: result.to_dict() if isinstance(result, CheckResult) else result
                for name, result in self.checks.items()
            },
        }


# ─────────────────────────────────────────────────────
# The Heartbeat — The Pulse Loop
# ─────────────────────────────────────────────────────

class HeartbeatDaemon:
    """The main heartbeat daemon. Runs the pulse loop and manages state.

    Usage:
        daemon = HeartbeatDaemon()
        daemon.run()  # Blocks until shutdown

    Or for a single pulse:
        daemon = HeartbeatDaemon()
        result = daemon.pulse()
        print(result)

    Or for status:
        daemon = HeartbeatDaemon()
        print(daemon.state)
    """

    def __init__(self, config: Optional[HeartbeatConfig] = None, daemon: bool = True):
        self.config = config or HeartbeatConfig()
        self.daemon_mode = daemon
        self.state = HeartbeatState()
        self.state.started_at = datetime.now(timezone.utc).isoformat()
        self.state.config_source = str(self.config.config_path)
        self.state.platform = get_platform_info().get("platform_name", "unknown")

        self._signal_handler = SignalHandler(
            config_reload_callback=self.config.reload,
            state_dump_callback=lambda: self.state.to_dict(),
        )
        self._daemon_ctx = DaemonContext(get_pid_path())

        # Initialize check instances from registry
        self._checks: dict[str, BaseCheck] = {}
        for name, check_class in CHECK_REGISTRY.items():
            if self.config.get(f"checks.{name}", True):
                self._checks[name] = check_class(self.config)

        self._running = False
        self._pulse_count = 0
        self._db_path = get_db_path()

    def run(self) -> None:
        """Main daemon loop. Blocks until shutdown."""
        ensure_dirs()
        self._setup_logging()

        logger.info(f"🫀 Verðandi Heartbeat starting (platform: {self.state.platform})")
        logger.info(f"   Config: {self.config}")
        logger.info(f"   Checks: {list(self._checks.keys())}")
        logger.info(f"   State dir: {get_state_dir()}")
        logger.info(f"   Pulse interval: {self.config.get('heartbeat.interval_seconds')}s")

        if self.daemon_mode:
            if not self._daemon_ctx.acquire():
                logger.error("Another instance is already running. Exiting.")
                return
            logger.info("Daemon mode: PID file acquired")

        self._signal_handler.install()
        self._state_db_init()
        self.state.state = DaemonState.RUNNING
        self._running = True

        # Startup delay
        startup_delay = self.config.get("heartbeat.startup_delay_seconds", 10)
        logger.info(f"Startup delay: {startup_delay}s")
        time.sleep(startup_delay)

        try:
            while self._running and not self._signal_handler.should_shutdown:
                # Handle signals
                if self._signal_handler.should_reload:
                    self._signal_handler.clear_reload()
                    self.config.reload()
                    # Re-initialize checks with new config
                    self._checks.clear()
                    for name, check_class in CHECK_REGISTRY.items():
                        if self.config.get(f"checks.{name}", True):
                            self._checks[name] = check_class(self.config)
                    logger.info("Config reloaded, checks re-initialized")

                if self._signal_handler.should_dump_state:
                    self._signal_handler.clear_dump_state()
                    self._signal_handler.dump_state(
                        self.state.to_dict(),
                        get_state_dir() / "verdandi_state_dump.json"
                    )

                # Run pulse
                self._pulse_count += 1
                self.pulse()

                # Update state machine
                self._update_daemon_state()

                # Sleep with jitter
                interval = self.config.get("heartbeat.interval_seconds", 60)
                jitter = self.config.get("heartbeat.jitter_seconds", 5)
                sleep_time = interval + random.uniform(-jitter, jitter)

                for _ in range(max(1, int(sleep_time))):
                    if self._signal_handler.should_shutdown:
                        break
                    if self._signal_handler.should_pulse:
                        self._signal_handler.clear_pulse()
                        break
                    if self._signal_handler.should_reload:
                        self._signal_handler.clear_reload()
                        self.config.reload()
                    time.sleep(1)

        finally:
            self.state.state = DaemonState.SHUTTING_DOWN
            self._shutdown()

    def pulse(self) -> HeartbeatState:
        """Run a single pulse cycle. Returns the state after the pulse."""
        start_time = time.monotonic()
        self.state.pulse_count += 1
        now = datetime.now(timezone.utc).isoformat()

        logger.debug(f"Pulse #{self.state.pulse_count} starting")

        # Run all enabled checks (graceful degradation)
        for name, check in self._checks.items():
            try:
                result = check.check()
                self.state.checks[name] = result
                logger.debug(f"Check {name}: {result.severity.value} — {result.message}")
            except Exception as e:
                logger.error(f"Check {name} failed: {e}")
                self.state.checks[name] = CheckResult(
                    name=name, severity=CheckSeverity.UNKNOWN,
                    message=f"Check error: {e}"
                )

        # Fire nerve impulse
        if self.config.get("nerve.publish_pulses", True):
            self._fire_nerve_pulse()

        # Persist state
        self.state.last_pulse = now
        if self.state.state in (DaemonState.RUNNING, DaemonState.RECOVERING):
            if all(
                r.severity in (CheckSeverity.OK, CheckSeverity.WARNING)
                for r in self.state.checks.values()
            ):
                self.state.last_healthy_pulse = now

        self.state.uptime_seconds = time.monotonic() - start_time + (
            self.state.uptime_seconds if self.state.pulse_count > 1 else 0
        )

        self._state_db_save()

        duration = (time.monotonic() - start_time) * 1000
        logger.info(
            f"🫀 Pulse #{self.state.pulse_count} complete "
            f"({duration:.0f}ms) state={self.state.state.value}"
        )

        return self.state

    def _update_daemon_state(self) -> None:
        """Update the daemon state machine based on check results."""
        prev_state = self.state.state

        # Determine worst severity
        severities = [r.severity for r in self.state.checks.values()]

        if any(s == CheckSeverity.CRITICAL for s in severities):
            new_state = DaemonState.CRITICAL
        elif any(s == CheckSeverity.WARNING for s in severities):
            new_state = DaemonState.DEGRADED
        elif any(s == CheckSeverity.UNKNOWN for s in severities):
            # Unknown checks don't change state
            new_state = self.state.state
            if new_state == DaemonState.INITIALIZING:
                new_state = DaemonState.RUNNING
        else:
            # All OK
            if self.state.state in (DaemonState.DEGRADED, DaemonState.CRITICAL):
                new_state = DaemonState.RECOVERING
            elif self.state.state == DaemonState.RECOVERING:
                new_state = DaemonState.RUNNING
            else:
                new_state = DaemonState.RUNNING

        if new_state != prev_state:
            logger.info(f"State transition: {prev_state.value} → {new_state.value}")
            self.state.state = new_state

            # State change → nerve impulse
            if self.config.get("nerve.publish_pulses", True):
                self._fire_nerve_state_change(prev_state, new_state)

    def _fire_nerve_pulse(self) -> None:
        """Fire a nerve impulse for the pulse event."""
        try:
            socket_path = self.config.get("nerve.socket_path") or str(get_socket_path())
            nerve_data = {
                "event_type": "heartbeat_pulse",
                "pulse_count": self.state.pulse_count,
                "state": self.state.state.value,
                "checks": {
                    name: {
                        "severity": result.severity.value,
                        "message": result.message,
                    }
                    for name, result in self.state.checks.items()
                },
            }

            import socket as sock_mod
            with sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM) as s:
                s.settimeout(2)
                s.connect(socket_path)
                s.sendall(json.dumps(nerve_data).encode() + b"\n")
        except Exception:
            if self.config.get("nerve.fallback_to_file", True):
                self._nerve_fallback_file(nerve_data if 'nerve_data' in dir() else {})

    def _fire_nerve_state_change(self, old_state: DaemonState, new_state: DaemonState) -> None:
        """Fire a nerve impulse for a state change."""
        try:
            socket_path = self.config.get("nerve.socket_path") or str(get_socket_path())
            nerve_data = {
                "event_type": "heartbeat_state_change",
                "old_state": old_state.value,
                "new_state": new_state.value,
                "pulse_count": self.state.pulse_count,
            }

            import socket as sock_mod
            with sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM) as s:
                s.settimeout(2)
                s.connect(socket_path)
                s.sendall(json.dumps(nerve_data).encode() + b"\n")
        except Exception:
            pass

    def _nerve_fallback_file(self, data: dict) -> None:
        """Fallback: append nerve impulse to file if socket unavailable."""
        try:
            feed_path = get_state_dir() / "nerve_feed.jsonl"
            with open(feed_path, "a") as f:
                entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "verdandi-heartbeat",
                    "event_type": data.get("event_type", "heartbeat_pulse"),
                    **data,
                }
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def _state_db_init(self) -> None:
        """Initialize the persistent state database."""
        db_path = self._db_path or get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS heartbeat_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pulse_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                state TEXT NOT NULL,
                checks_json TEXT,
                pulse_count INTEGER
            )
        """)
        conn.commit()
        conn.close()

    def _state_db_save(self) -> None:
        """Persist current state to database."""
        try:
            db_path = self._db_path or get_db_path()
            conn = sqlite3.connect(str(db_path))

            state_dict = self.state.to_dict()
            for key, value in state_dict.items():
                if isinstance(value, dict):
                    value = json.dumps(value)
                elif isinstance(value, Enum):
                    value = value.value
                conn.execute(
                    "INSERT OR REPLACE INTO heartbeat_state (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                    (key, str(value) if not isinstance(value, (str, int, float)) else value)
                )

            checks_json = json.dumps(state_dict.get("checks", {}))
            conn.execute(
                "INSERT INTO pulse_history (timestamp, state, checks_json, pulse_count) VALUES (datetime('now'), ?, ?, ?)",
                (state_dict["state"], checks_json, state_dict.get("pulse_count", 0))
            )
            conn.execute("DELETE FROM pulse_history WHERE id < (SELECT MAX(id) FROM pulse_history) - 1000")

            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"State DB save failed: {e}")

    def _setup_logging(self) -> None:
        """Configure logging for the daemon."""
        log_level = self.config.get("logging.level", "INFO")
        log_format = self.config.get("logging.format", "%(asctime)s [%(levelname)s] %(name)s: %(message)s")

        log_path = get_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)

        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=self.config.get("logging.file_max_bytes", 10 * 1024 * 1024),
            backupCount=self.config.get("logging.file_backup_count", 5),
        )
        file_handler.setFormatter(logging.Formatter(log_format))
        file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))

        root_logger = logging.getLogger("verdandi")
        root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        root_logger.addHandler(file_handler)

        if self.config.get("logging.also_log_to_stderr", True):
            stderr_handler = logging.StreamHandler()
            stderr_handler.setFormatter(logging.Formatter(log_format))
            stderr_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
            root_logger.addHandler(stderr_handler)

    def _shutdown(self) -> None:
        """Clean up on shutdown."""
        logger.info("Shutting down...")
        self.state.state = DaemonState.SHUTTING_DOWN
        self._state_db_save()

        if self.daemon_mode:
            self._daemon_ctx.release()

        self._signal_handler.restore()
        self._running = False
        logger.info("🫀 Verðandi Heartbeat stopped. The pulse is silent for now.")