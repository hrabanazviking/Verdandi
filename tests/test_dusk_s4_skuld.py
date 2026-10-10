"""Dusk S4 — Skuld `_predict_capacity` capacity regression tests.

Reproduces the confirmed bug: `_predict_capacity` always returned
`{"status": "no_resource_data"}` even with 12 rows of rising disk/RAM
history, because:
  (a) it read Eir's metrics off the outer CheckResult dict instead of the
      nested `["health"]["details"]` dict; and
  (b) it looked for `memory_used_percent` while Eir writes `ram_used_percent`.

These tests seed a temp DB with the REAL Eir checks_json shape —
`{"health": CheckResult(name="health", details={...}).to_dict()}` —
exactly as core.py's `_state_db_save` serializes it, and verify real
predictions come out, plus the graceful paths when data is absent.
"""

import copy
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from heartbeat.checks.base import CheckResult, CheckSeverity
from heartbeat.checks.skuld import SkuldCheck
from heartbeat.config import DEFAULTS, HeartbeatConfig


# ============================================================================
# Helpers
# ============================================================================

def _make_config(db_path: Path) -> HeartbeatConfig:
    """HeartbeatConfig pointing heartbeat.db_path at a temp DB."""
    config = HeartbeatConfig.__new__(HeartbeatConfig)
    config._config_path = Path("/tmp/nonexistent_heartbeat_config.yaml")
    config._raw = {}
    config._env_overrides = {}
    config._loaded = True
    config._config = copy.deepcopy(DEFAULTS)
    config.set("heartbeat.db_path", str(db_path))
    return config


def _eir_checks_json(disk_pct: float, ram_pct: float) -> str:
    """Real Eir serialization shape.

    core.py `_state_db_save` stores:
        json.dumps({"health": <EirCheck CheckResult>.to_dict(), ...})
    Eir writes `ram_used_percent` / `disk_used_percent` inside
    the CheckResult's `details` dict (see EirCheck._perform_check).
    """
    result = CheckResult(
        name="health",
        severity=CheckSeverity.OK,
        message="All health checks passing",
        details={
            "cpu_temp_c": 45.0,
            "ram_used_percent": ram_pct,
            "ram_total_gb": 16.0,
            "ram_available_gb": 8.0,
            "disk_used_percent": disk_pct,
            "disk_total_gb": 100.0,
            "disk_free_gb": 50.0,
        },
    )
    return json.dumps({"health": result.to_dict()})


def _seed_pulse_history(db_path: Path, rows: list[str]) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE pulse_history "
            "(id INTEGER PRIMARY KEY, timestamp TEXT, state TEXT, "
            "checks_json TEXT, pulse_count INTEGER)"
        )
        now = datetime.now(timezone.utc)
        for i, checks_json in enumerate(rows):
            ts = (now - timedelta(minutes=len(rows) - i)).isoformat()
            conn.execute(
                "INSERT INTO pulse_history "
                "(timestamp, state, checks_json, pulse_count) "
                "VALUES (?, ?, ?, ?)",
                (ts, "running", checks_json, i + 1),
            )
        conn.commit()


# ============================================================================
# Tests
# ============================================================================

class TestSkuldCapacityPrediction:
    """The S4 acceptance cases."""

    def test_rising_disk_and_ram_yield_real_predictions(self, tmp_path):
        """12 rows of rising disk/RAM in the real Eir shape must not hit
        the dead `no_resource_data` path — real day numbers must come out."""
        db = tmp_path / "verdandi_heartbeat.db"
        rows = [
            _eir_checks_json(disk_pct=30.0 + i * 1.5, ram_pct=40.0 + i * 1.0)
            for i in range(12)
        ]
        _seed_pulse_history(db, rows)

        skuld = SkuldCheck(_make_config(db))
        result = skuld._predict_capacity()

        assert "status" not in result, f"dead path returned: {result}"

        assert "disk" in result
        disk = result["disk"]
        assert disk["prediction"] == "exhaustion_predicted"
        assert isinstance(disk["days_to_threshold"], (int, float))
        assert isinstance(disk["days_to_exhaustion"], (int, float))
        assert disk["days_to_threshold"] == disk["days_to_exhaustion"]
        # rising disk must be consuming, not "decreasing_or_stable"
        assert disk["slope_per_pulse"] > 0

        assert "memory" in result
        assert result["memory"]["prediction"] == "exhaustion_predicted"
        assert isinstance(result["memory"]["days_to_exhaustion"], (int, float))

    def test_rows_without_resource_metrics_return_no_resource_data(self, tmp_path):
        """Rows in the real shape but without disk/ram metrics genuinely
        carry no resource data — the graceful path must survive."""
        db = tmp_path / "verdandi_heartbeat.db"
        rows = [
            json.dumps({
                "health": CheckResult(
                    name="health",
                    severity=CheckSeverity.OK,
                    message="ok",
                    details={"cpu_temp_c": 42.0},  # no disk/ram metrics
                ).to_dict()
            })
            for _ in range(12)
        ]
        _seed_pulse_history(db, rows)

        skuld = SkuldCheck(_make_config(db))
        assert skuld._predict_capacity() == {"status": "no_resource_data"}

    def test_empty_table_stays_graceful(self, tmp_path):
        """A DB with no pulse rows at all must not explode."""
        db = tmp_path / "verdandi_heartbeat.db"
        with sqlite3.connect(str(db)) as conn:
            conn.execute(
                "CREATE TABLE pulse_history "
                "(id INTEGER PRIMARY KEY, timestamp TEXT, state TEXT, "
                "checks_json TEXT, pulse_count INTEGER)"
            )
            conn.commit()

        skuld = SkuldCheck(_make_config(db))
        assert skuld._predict_capacity() == {
            "status": "insufficient_data",
            "minimum_required": 10,
        }

    def test_legacy_memory_key_still_accepted(self, tmp_path):
        """Rows seeded by other writers with `memory_used_percent` still
        produce memory predictions (backward-compatible alias)."""
        db = tmp_path / "verdandi_heartbeat.db"
        rows = []
        for i in range(12):
            result = CheckResult(
                name="health",
                severity=CheckSeverity.OK,
                message="ok",
                details={
                    "disk_used_percent": 30.0 + i * 1.5,
                    "memory_used_percent": 40.0 + i * 1.0,
                },
            )
            rows.append(json.dumps({"health": result.to_dict()}))
        _seed_pulse_history(db, rows)

        skuld = SkuldCheck(_make_config(db))
        result = skuld._predict_capacity()

        assert "status" not in result
        assert result["memory"]["prediction"] == "exhaustion_predicted"
        assert isinstance(result["memory"]["days_to_exhaustion"], (int, float))
