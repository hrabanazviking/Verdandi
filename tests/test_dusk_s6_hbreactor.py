"""
Dusk run S7+S8 tests — Verðandi "The Kept Oath".

S7: No default reactor rule may reference an unregistered action.
    The v0.4.0 DISCIPLINE rule (projects/WARNING+ → discipline_enforcement)
    must resolve to the registered HeimdallAction.
S8: MetricsRegistry.update_from_state() must actually set
    verdandi_circuit_breaker_state and verdandi_prediction_days_to_exhaustion
    (both were registered with HELP/TYPE but never .set()).
"""

import logging
from pathlib import Path
import sys

import pytest

PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from heartbeat.actions.base import ACTION_REGISTRY
from heartbeat.checks.base import CheckResult, CheckSeverity
from heartbeat.prometheus import MetricsRegistry
from heartbeat.reactor import Reactor


def make_check_result(name="test", severity=CheckSeverity.OK,
                      message="ok", details=None):
    return CheckResult(
        name=name,
        severity=severity,
        message=message,
        details=details or {},
    )


def representative_state():
    """Representative heartbeat state dict for the prometheus tests."""
    return {
        "state": "running",
        "pulse_count": 42,
        "health_score": 87.5,
        "health_trend": "stable",
        "emotional_state": "moderate",
        "circuit_breakers": {
            "projects": "closed",
            "schedule": "open",
            "memory": "half_open",
        },
        "checks": {
            "projects": {
                "name": "projects",
                "severity": "warning",
                "message": "dirty repos",
                "details": {},
            },
            "prediction": {
                "name": "prediction",
                "severity": "warning",
                "message": "capacity risk",
                "details": {
                    "capacity": {
                        "disk": {
                            "prediction": "exhaustion_predicted",
                            "days_to_threshold": 4.2,
                            "urgency": "critical",
                        },
                        "memory": {
                            "prediction": "exhaustion_predicted",
                            "days_to_threshold": 61.0,
                            "urgency": "info",
                        },
                        "temp": {"prediction": "insufficient_data",
                                 "data_points": 2},
                    },
                },
            },
        },
    }


# ─────────────────────────────────────────────────────
# S7 — discipline rule wiring honesty
# ─────────────────────────────────────────────────────

class TestS7DisciplineRule:
    def test_discipline_enforcement_is_registered(self):
        """The discipline rule's action must exist in the registry."""
        assert "discipline_enforcement" in ACTION_REGISTRY
        assert "discipline_enforcement" in Reactor().actions

    def test_no_default_rule_references_unregistered_action(self):
        """Every default rule's action_name must resolve to an action."""
        reactor = Reactor()
        unregistered = [
            rule.action_name
            for rule in reactor.rules
            if rule.action_name not in reactor.actions
        ]
        assert unregistered == []

    def test_projects_warning_fires_discipline_action(self, caplog):
        """A projects WARNING event fires the discipline (Heimdall) action
        with no 'not found in registry' warning."""
        reactor = Reactor(dry_run=True)
        results = {
            "projects": make_check_result(
                "projects", CheckSeverity.WARNING, "dirty repos"),
        }
        with caplog.at_level(logging.WARNING, logger="verdandi.heartbeat.reactor"):
            action_results = reactor.react(results)
        # No "not found in registry" log lines
        assert not any(
            "not found in registry" in record.getMessage()
            for record in caplog.records
        )
        # The discipline action (Heimdall) actually fired alongside auto_push
        fired = [ar.action_name for ar in action_results]
        assert "heimdall" in fired
        assert "auto_push" in fired


# ─────────────────────────────────────────────────────
# S8 — prometheus gauges actually set
# ─────────────────────────────────────────────────────

class TestS8PrometheusGauges:
    def test_circuit_breaker_series(self):
        registry = MetricsRegistry()
        registry.update_from_state(representative_state())
        rendered = registry.render()
        assert 'verdandi_circuit_breaker_state{check="projects"} 0' in rendered
        assert 'verdandi_circuit_breaker_state{check="schedule"} 1' in rendered
        assert 'verdandi_circuit_breaker_state{check="memory"} 0.5' in rendered

    def test_prediction_days_to_exhaustion_series(self):
        registry = MetricsRegistry()
        registry.update_from_state(representative_state())
        rendered = registry.render()
        assert 'verdandi_prediction_days_to_exhaustion{resource="disk"} 4.2' in rendered
        assert 'verdandi_prediction_days_to_exhaustion{resource="memory"} 61.0' in rendered
        # No series for resources without a numeric days_to_threshold
        assert '{resource="temp"}' not in rendered

    def test_gauges_tolerate_missing_sections(self):
        """A state dict without breakers/predictions must not crash."""
        registry = MetricsRegistry()
        registry.update_from_state({"checks": {}, "health_score": 90})
        rendered = registry.render()
        assert "verdandi_circuit_breaker_state" in rendered  # HELP/TYPE still there
        assert "verdandi_prediction_days_to_exhaustion" in rendered
