"""
Dusk run "The Kept Oath" — S5 + S6 regression tests for heartbeat/core.py.

S5: overnight maintenance windows (e.g. 22:00–02:00) must actually match;
    `_time_in_window` keeps the wrap-midnight logic unit-testable.
S6: a daemon with zero enabled checks must not report perfect health —
    state UNKNOWN, health score None (never 100.0), and no healthy-pulse stamp.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from heartbeat.core import (
    DaemonState,
    HealthScore,
    HeartbeatDaemon,
    HeartbeatState,
    _time_in_window,
)
from heartbeat.config import HeartbeatConfig
from heartbeat.checks.base import CheckResult, CheckSeverity
from heartbeat.paths import reset_paths
from heartbeat.signals import SignalHandler, DaemonContext


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_paths():
    reset_paths()
    yield
    reset_paths()


def _frozen_datetime(year, month, day, hour, minute):
    """Return a datetime subclass whose now() is pinned to the given UTC time."""

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(year, month, day, hour, minute, 0, tzinfo=timezone.utc)

    return _Frozen


@pytest.fixture
def bare_daemon(tmp_path, monkeypatch):
    """Minimal HeartbeatDaemon (no checks) suitable for pulse()/state tests."""
    monkeypatch.setenv("VERDANDI_HOME", str(tmp_path))
    reset_paths()

    daemon = HeartbeatDaemon.__new__(HeartbeatDaemon)
    daemon.config = HeartbeatConfig()
    daemon.config.set("nerve.publish_pulses", False)
    daemon.config.set("reactor.enabled", False)
    daemon.daemon_mode = False
    daemon.state = HeartbeatState()
    daemon.state.started_at = datetime.now(timezone.utc).isoformat()
    daemon._signal_handler = SignalHandler()
    daemon._daemon_ctx = DaemonContext(tmp_path / "run" / "test.pid")
    daemon._checks = {}
    daemon._circuit_breakers = {}
    daemon._health_score = HealthScore()
    daemon._reactor = MagicMock()
    daemon._maintenance_windows = []
    daemon._maintenance_suppress_actions = True
    daemon._maintenance_suppress_checks = []
    daemon._prometheus = None
    daemon._running = False
    daemon._pulse_count = 0
    daemon._db_path = tmp_path / "test.db"
    return daemon


def _maintenance_daemon(windows):
    """MagicMock daemon carrying maintenance windows, for _in_maintenance_window."""
    daemon = MagicMock()
    daemon._maintenance_windows = windows
    return daemon


# ============================================================================
# S5 — _time_in_window unit tests
# ============================================================================


class TestTimeInWindow:
    """Direct unit tests of the wrap-midnight helper."""

    def test_overnight_contains_0100(self):
        assert _time_in_window("22:00", "02:00", "01:00") is True

    def test_overnight_contains_2300(self):
        assert _time_in_window("22:00", "02:00", "23:00") is True

    def test_overnight_excludes_1200(self):
        assert _time_in_window("22:00", "02:00", "12:00") is False

    def test_overnight_boundaries_inclusive(self):
        assert _time_in_window("22:00", "02:00", "22:00") is True
        assert _time_in_window("22:00", "02:00", "02:00") is True

    def test_daytime_window_normal(self):
        assert _time_in_window("09:00", "17:00", "12:00") is True
        assert _time_in_window("09:00", "17:00", "18:00") is False
        assert _time_in_window("09:00", "17:00", "08:59") is False

    def test_daytime_boundaries_inclusive(self):
        assert _time_in_window("09:00", "17:00", "09:00") is True
        assert _time_in_window("09:00", "17:00", "17:00") is True


# ============================================================================
# S5 — _in_maintenance_window with frozen clock
# ============================================================================


class TestMaintenanceWindowOvernight:
    """Overnight windows must match across midnight (tz-aware UTC now)."""

    WINDOW = [{"day": "daily", "start": "22:00", "end": "02:00"}]

    def _at(self, monkeypatch, hour, minute, windows=None):
        monkeypatch.setattr(
            "heartbeat.core.datetime",
            _frozen_datetime(2026, 10, 10, hour, minute),  # a Saturday
        )
        return HeartbeatDaemon._in_maintenance_window(
            _maintenance_daemon(self.WINDOW if windows is None else windows)
        )

    def test_overnight_matches_0100(self, monkeypatch):
        assert self._at(monkeypatch, 1, 0) is True

    def test_overnight_matches_2300(self, monkeypatch):
        assert self._at(monkeypatch, 23, 0) is True

    def test_overnight_excludes_noon(self, monkeypatch):
        assert self._at(monkeypatch, 12, 0) is False

    def test_day_filter_still_applies(self, monkeypatch):
        windows = [{"day": "sunday", "start": "22:00", "end": "02:00"}]
        # 2026-10-10 is a Saturday — a Sunday-only window must not match
        assert self._at(monkeypatch, 1, 0, windows) is False

    def test_matching_day_and_window(self, monkeypatch):
        windows = [{"day": "saturday", "start": "22:00", "end": "02:00"}]
        assert self._at(monkeypatch, 1, 0, windows) is True

    def test_full_day_window_still_matches(self, monkeypatch):
        windows = [{"day": "daily", "start": "00:00", "end": "23:59"}]
        assert self._at(monkeypatch, 12, 30, windows) is True


# ============================================================================
# S6 — zero checks must not claim perfect health
# ============================================================================


class TestHealthScoreNoChecks:
    """HealthScore refuses to invent a score when nothing is being watched."""

    def test_record_pulse_empty_returns_none_not_100(self):
        hs = HealthScore()
        assert hs.record_pulse({}) is None

    def test_empty_pulse_records_no_sample(self):
        hs = HealthScore()
        hs.record_pulse({})
        assert hs.summary["sample_count"] == 0
        assert hs.summary["no_checks"] is True

    def test_current_is_none_before_any_data(self):
        assert HealthScore().current is None

    def test_normal_path_still_scores(self):
        hs = HealthScore()
        result = CheckResult(name="health", severity=CheckSeverity.OK)
        assert hs.record_pulse({"health": result}) == 100.0
        assert hs.current == 100.0
        assert hs.summary["no_checks"] is False

    def test_empty_pulse_does_not_move_ema(self):
        hs = HealthScore()
        result = CheckResult(name="health", severity=CheckSeverity.OK)
        hs.record_pulse({"health": result})
        before = hs.current
        hs.record_pulse({})
        assert hs.current == before


class TestZeroChecksDaemon:
    """A daemon with zero enabled checks reports UNKNOWN, not RUNNING."""

    def test_unknown_state_value(self):
        assert DaemonState.UNKNOWN.value == "unknown"

    def test_zero_checks_state_is_unknown(self, bare_daemon):
        bare_daemon.state.state = DaemonState.INITIALIZING
        bare_daemon.state.checks = {}
        bare_daemon._update_daemon_state()
        assert bare_daemon.state.state == DaemonState.UNKNOWN

    def test_zero_checks_pulse_never_claims_health(self, bare_daemon):
        # Mirror the recon repro: all checks disabled, 2 pulses.
        bare_daemon.state.state = DaemonState.RUNNING
        for _ in range(2):
            bare_daemon.pulse()
            bare_daemon._update_daemon_state()

        assert bare_daemon.state.state == DaemonState.UNKNOWN
        assert bare_daemon._health_score.current is None  # not 100.0
        assert bare_daemon.state.last_healthy_pulse == ""  # never stamped
        assert bare_daemon._health_score.summary["no_checks"] is True

    def test_daemon_recovers_to_running_when_checks_appear(self, bare_daemon):
        bare_daemon.state.state = DaemonState.UNKNOWN
        bare_daemon.state.checks["health"] = CheckResult(
            name="health", severity=CheckSeverity.OK
        )
        bare_daemon._update_daemon_state()
        assert bare_daemon.state.state == DaemonState.RUNNING

    def test_healthy_pulse_still_stamped_with_checks(self, bare_daemon, monkeypatch):
        """Normal path unaffected: passing checks still stamp last_healthy_pulse."""
        monkeypatch.setattr(
            "heartbeat.core.datetime", _frozen_datetime(2026, 10, 10, 3, 0)
        )
        bare_daemon.state.state = DaemonState.RUNNING
        bare_daemon.state.checks = {
            "health": CheckResult(name="health", severity=CheckSeverity.OK)
        }
        bare_daemon.pulse()
        assert bare_daemon.state.last_healthy_pulse != ""
        assert bare_daemon._health_score.current == 100.0
