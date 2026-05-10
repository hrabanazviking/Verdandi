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
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field, asdict

from heartbeat.config import HeartbeatConfig, DEFAULTS
from heartbeat.paths import (
    get_state_dir, get_log_dir, get_pid_dir, get_socket_path,
    get_config_path, get_db_path, get_pid_path, get_log_path,
    get_platform_info, ensure_dirs,
)
from heartbeat.signals import SignalHandler, DaemonContext

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


class PulseSeverity(Enum):
    """Severity levels for individual check results."""
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class PulseResult:
    """Result of a single health check pulse."""
    name: str
    severity: PulseSeverity = PulseSeverity.OK
    message: str = ""
    details: dict = field(default_factory=dict)
    timestamp: str = ""
    duration_ms: float = 0.0
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class HeartbeatState:
    """Full state snapshot of the daemon."""
    state: DaemonState = DaemonState.INITIALIZING
    pulse_count: int = 0
    last_pulse: str = ""
    last_healthy_pulse: str = ""
    started_at: str = ""
    checks: dict[str, PulseResult] = field(default_factory=dict)
    uptime_seconds: float = 0.0
    config_source: str = ""
    platform: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        d = asdict(self)
        d["state"] = self.state.value
        d["checks"] = {
            k: {kk: (vv.value if isinstance(vv, PulseSeverity) else vv) 
                for kk, vv in v.items()} if isinstance(v, dict) else 
               (vv.value if isinstance(vv, PulseSeverity) else vv)
            for k, v in d["checks"].items()
        }
        return d


# ─────────────────────────────────────────────────────
# Health Checks — The Senses
# ─────────────────────────────────────────────────────

class HealthCheck:
    """System health check: CPU temp, RAM, disk space."""
    
    def __init__(self, config: HeartbeatConfig):
        self.config = config
    
    def check(self) -> PulseResult:
        """Run all health checks and return the worst result."""
        start = time.monotonic()
        issues = []
        details = {}
        
        # CPU temperature
        temp = self._get_cpu_temp()
        if temp is not None:
            details["cpu_temp_c"] = temp
            warn = self.config.get("thresholds.cpu_temp_warning", 70)
            crit = self.config.get("thresholds.cpu_temp_critical", 80)
            if temp >= crit:
                issues.append(("critical", f"CPU temp {temp}°C >= {crit}°C"))
            elif temp >= warn:
                issues.append(("warning", f"CPU temp {temp}°C >= {warn}°C"))
        
        # RAM usage
        ram = self._get_ram_usage()
        if ram:
            details["ram_used_percent"] = ram["percent"]
            details["ram_total_gb"] = ram["total_gb"]
            details["ram_available_gb"] = ram["available_gb"]
            warn = self.config.get("thresholds.ram_warning_percent", 85)
            crit = self.config.get("thresholds.ram_critical_percent", 95)
            if ram["percent"] >= crit:
                issues.append(("critical", f"RAM {ram['percent']:.1f}% >= {crit}%"))
            elif ram["percent"] >= warn:
                issues.append(("warning", f"RAM {ram['percent']:.1f}% >= {warn}%"))
        
        # Disk usage
        disk = self._get_disk_usage()
        if disk:
            details["disk_used_percent"] = disk["percent"]
            details["disk_total_gb"] = disk["total_gb"]
            details["disk_free_gb"] = disk["free_gb"]
            warn = self.config.get("thresholds.disk_warning_percent", 80)
            crit = self.config.get("thresholds.disk_critical_percent", 90)
            if disk["percent"] >= crit:
                issues.append(("critical", f"Disk {disk['percent']:.1f}% >= {crit}%"))
            elif disk["percent"] >= warn:
                issues.append(("warning", f"Disk {disk['percent']:.1f}% >= {warn}%"))
        
        # Determine worst severity
        severity = PulseSeverity.OK
        message = "All health checks passing"
        for level, msg in issues:
            if level == "critical":
                severity = PulseSeverity.CRITICAL
                message = msg
                break
            elif level == "warning" and severity != PulseSeverity.CRITICAL:
                severity = PulseSeverity.WARNING
                message = msg
        
        if not issues:
            # Pi-specific: note if running on Pi
            pinfo = get_platform_info()
            if pinfo.get("is_pi"):
                message = f"All health checks passing (Pi, {temp}°C)" if temp else "All health checks passing (Pi)"
        
        duration = (time.monotonic() - start) * 1000
        return PulseResult(
            name="health",
            severity=severity,
            message=message,
            details=details,
            duration_ms=duration,
        )
    
    def _get_cpu_temp(self) -> Optional[float]:
        """Get CPU temperature in °C. Returns None if unavailable."""
        # Try /sys/class/thermal (Linux/Pi)
        for thermal_zone in Path("/sys/class/thermal").glob("thermal_zone*"):
            try:
                temp_millic = int((thermal_zone / "temp").read_text().strip())
                return temp_millic / 1000.0
            except (FileNotFoundError, ValueError, PermissionError):
                continue
        
        # Try vcgencmd (Raspberry Pi specific)
        try:
            import subprocess
            result = subprocess.run(
                ["vcgencmd", "measure_temp"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                # Output: "temp=47.2'C"
                temp_str = result.stdout.strip().split("=")[1].split("'")[0]
                return float(temp_str)
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
            pass
        
        # Try /proc/device-tree (Pi)
        try:
            # Not temperature but can infer Pi is running
            Path("/proc/device-tree/model").read_text()
            # On Pi but can't get temp — return None, not an error
        except (FileNotFoundError, PermissionError):
            pass
        
        return None
    
    def _get_ram_usage(self) -> Optional[dict]:
        """Get RAM usage statistics."""
        try:
            with open("/proc/meminfo") as f:
                meminfo = {}
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(":")
                        value = int(parts[1])  # in kB
                        meminfo[key] = value
            
            total = meminfo.get("MemTotal", 0)
            available = meminfo.get("MemAvailable", 0)
            
            if total == 0:
                return None
            
            used_percent = ((total - available) / total) * 100
            return {
                "total_kb": total,
                "available_kb": available,
                "total_gb": round(total / 1024 / 1024, 1),
                "available_gb": round(available / 1024 / 1024, 1),
                "percent": round(used_percent, 1),
            }
        except (FileNotFoundError, ValueError, PermissionError):
            return None
    
    def _get_disk_usage(self) -> Optional[dict]:
        """Get disk usage for the root partition."""
        try:
            import shutil
            usage = shutil.disk_usage("/")
            total_gb = usage.total / (1024**3)
            free_gb = usage.free / (1024**3)
            used_gb = usage.used / (1024**3)
            percent = (usage.used / usage.total) * 100
            
            return {
                "total_gb": round(total_gb, 1),
                "used_gb": round(used_gb, 1),
                "free_gb": round(free_gb, 1),
                "percent": round(percent, 1),
            }
        except Exception:
            return None


# ─────────────────────────────────────────────────────
# The Heartbeat — The Pulse Loop
# ─────────────────────────────────────────────────────

class HeartbeatDaemon:
    """The main heartbeat daemon. Runs the pulse loop and manages state.
    
    Usage:
        daemon = HeartbeatDaemon()
        daemon.run()  # Blocks until shutdown
    
    Or programmatically:
        daemon = HeartbeatDaemon()
        daemon.start()  # Starts in background
    
    Or for a single pulse:
        daemon = HeartbeatDaemon()
        result = daemon.pulse()
        print(result)
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
        self._health_check = HealthCheck(self.config)
        self._running = False
        self._pulse_count = 0
        
        # DB for persistent state
        self._db_path = get_db_path()
    
    def run(self) -> None:
        """Main daemon loop. Blocks until shutdown.
        
        This is the heart that beats. Every pulse:
          1. Check for signals (SIGHUP, SIGUSR1, SIGUSR2)
          2. Run all enabled health checks
          3. Update state machine
          4. Fire nerve impulse
          5. Take recovery actions if needed
          6. Sleep until next pulse
        """
        ensure_dirs()
        self._setup_logging()
        
        logger.info(f"🫀 Verðandi Heartbeat starting (platform: {self.state.platform})")
        logger.info(f"   Config: {self.config}")
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
        logger.info(f"Startup delay: {startup_delays}s")
        time.sleep(startup_delay)
        
        try:
            while self._running and not self._signal_handler.should_shutdown:
                # Handle signals
                if self._signal_handler.should_reload:
                    self._signal_handler.clear_reload()
                    self.config.reload()
                    logger.info("Config reloaded")
                
                if self._signal_handler.should_dump_state:
                    self._signal_handler.clear_dump_state()
                    self._signal_handler.dump_state(
                        self.state.to_dict(),
                        get_state_dir() / "verdandi_state_dump.json"
                    )
                
                # Run pulse
                self._pulse_count += 1
                self.pulse()
                
                # Recover state if possible
                self._update_daemon_state()
                
                # Sleep with jitter to prevent thundering herd
                interval = self.config.get("heartbeat.interval_seconds", 60)
                jitter = self.config.get("heartbeat.jitter_seconds", 5)
                sleep_time = interval + random.uniform(-jitter, jitter)
                
                # Interruptible sleep — check shutdown flag every second
                for _ in range(max(1, int(sleep_time))):
                    if self._signal_handler.should_shutdown:
                        break
                    # Handle pending signals during sleep
                    if self._signal_handler.should_pulse:
                        self._signal_handler.clear_pulse()
                        break  # Skip remaining sleep, pulse immediately
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
        
        # Health check (always enabled, fundamental)
        if self.config.get("checks.health", True):
            try:
                result = self._health_check.check()
                self.state.checks["health"] = result
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                self.state.checks["health"] = PulseResult(
                    name="health", severity=PulseSeverity.UNKNOWN,
                    message=f"Check error: {e}"
                )
        
        # Fire nerve impulse
        if self.config.get("nerve.publish_pulses", True):
            self._fire_nerve_pulse()
        
        # Persist state
        self.state.last_pulse = now
        if self.state.state in (DaemonState.RUNNING, DaemonState.RECOVERING):
            if all(
                r.severity in (PulseSeverity.OK, PulseSeverity.WARNING)
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
        
        if any(s == PulseSeverity.CRITICAL for s in severities):
            new_state = DaemonState.CRITICAL
        elif any(s == PulseSeverity.WARNING for s in severities):
            new_state = DaemonState.DEGRADED
        elif any(s == PulseSeverity.UNKNOWN for s in severities):
            # Unknown checks don't change state
            new_state = self.state.state
            if new_state == DaemonState.INITIALIZING:
                new_state = DaemonState.RUNNING
        else:
            # All OK
            if self.state.state in (DaemonState.DEGRADED, DaemonState.CRITICAL):
                new_state = DaemonState.RECOVERING
            elif self.state.state == DaemonState.RECOVERING:
                new_state = DaemonState.RUNNING  # Stay recovering for one more pulse
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
            # Nerve hub unavailable — non-critical
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
            pass  # Truly non-critical
    
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
            
            # Save current state
            state_dict = self.state.to_dict()
            for key, value in state_dict.items():
                if key == "checks":
                    value = json.dumps({
                        k: {"severity": v.severity.value, "message": v.message, "details": v.details}
                        for k, v in value.items()
                    } if isinstance(value, dict) else value)
                elif isinstance(value, Enum):
                    value = value.value
                conn.execute(
                    "INSERT OR REPLACE INTO heartbeat_state (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                    (key, str(value) if not isinstance(value, str) else value)
                )
            
            # Save pulse history (keep last 1000)
            checks_json = json.dumps({
                name: {"severity": r.severity.value, "message": r.message}
                for name, r in self.state.checks.items()
            })
            conn.execute(
                "INSERT INTO pulse_history (timestamp, state, checks_json, pulse_count) VALUES (datetime('now'), ?, ?, ?)",
                (self.state.state.value, checks_json, self.state.pulse_count)
            )
            # Trim history to last 1000 entries
            conn.execute("DELETE FROM pulse_history WHERE id < (SELECT MAX(id) FROM pulse_history) - 1000")
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"State DB save failed: {e}")
    
    def _setup_logging(self) -> None:
        """Configure logging for the daemon."""
        log_level = self.config.get("logging.level", "INFO")
        log_format = self.config.get("logging.format", "%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        
        # File handler
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
        
        # Root logger
        root_logger = logging.getLogger("verdandi")
        root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        root_logger.addHandler(file_handler)
        
        # Also log to stderr for systemd/journal
        if self.config.get("logging.also_log_to_stderr", True):
            stderr_handler = logging.StreamHandler()
            stderr_handler.setFormatter(logging.Formatter(log_format))
            stderr_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
            root_logger.addHandler(stderr_handler)
    
    def _shutdown(self) -> None:
        """Clean up on shutdown."""
        logger.info("Shutting down...")
        
        # Save final state
        self.state.state = DaemonState.SHUTTING_DOWN
        self._state_db_save()
        
        # Release PID file
        if self.daemon_mode:
            self._daemon_ctx.release()
        
        # Restore signal handlers
        self._signal_handler.restore()
        
        self._running = False
        logger.info("🫀 Verðandi Heartbeat stopped. The pulse is silent for now.")