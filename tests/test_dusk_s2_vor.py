"""Dusk run S2 — Verðandi VörAction defect tests.

Covers:
  (a) VörAction no longer overrides BaseAction.execute: the no-action
      branch must return a proper ActionResult (real ActionSeverity member,
      correct `action_name` field) without raising; an internally-raising
      action must be caught by BaseAction.execute's guard so Reactor.react()
      — and therefore core.pulse() — can never be killed by it.
  (b) _get_capacity_summary (and the _execute capacity loop) must tolerate
      non-dict capacity entries (e.g. "status" strings).
"""
import pytest

from heartbeat.actions.base import (
    ActionContext, ActionResult, ActionSeverity,
)
from heartbeat.actions.vor_action import VörAction
from heartbeat.checks.base import CheckResult, CheckSeverity
from heartbeat.reactor import Reactor, ReactionRule


def _ctx(capacity=None, dry_run=False, trigger_name="prediction",
         trigger_severity=CheckSeverity.WARNING):
    details = {"capacity": capacity} if capacity is not None else {}
    trigger = CheckResult(
        name=trigger_name, severity=trigger_severity,
        message="trigger", details=details,
    )
    return ActionContext(
        trigger_check=trigger_name,
        trigger_result=trigger,
        all_results={trigger_name: trigger},
        dry_run=dry_run,
    )


class _ExplodingVör(VörAction):
    """VörAction whose core logic blows up — the guard must catch it."""

    name = "exploding_vor"

    def should_trigger(self, context):
        return True  # always trigger; the test is about the execute guard

    def _execute(self, context):
        raise RuntimeError("simulated action failure")


# ─────────────────────────────────────────────────────
# (a) No-prediction path returns a proper ActionResult
# ─────────────────────────────────────────────────────

def test_no_predictions_returns_result_without_raising():
    """Calling the action with no predictions must not raise AttributeError."""
    action = VörAction()
    result = action.execute(_ctx(capacity={}))
    assert isinstance(result, ActionResult)
    assert result.action_name == "preemptive_heal"
    assert isinstance(result.severity, ActionSeverity)  # real enum member
    assert result.severity == ActionSeverity.SKIPPED
    assert result.message  # non-empty message


def test_no_urgent_predictions_returns_result_without_raising():
    """Dict capacity entries with no warning/critical urgency → clean result."""
    action = VörAction()
    capacity = {
        "disk": {"urgency": "ok", "prediction": "45% in 90d"},
        "memory": {"urgency": "ok", "prediction": "60% in 60d"},
    }
    result = action.execute(_ctx(capacity=capacity))
    assert isinstance(result, ActionResult)
    assert result.severity == ActionSeverity.SKIPPED


def test_dry_run_wrapper_restored():
    """BaseAction.execute must route dry-run through _dry_run (DRY_RUN result)."""
    action = VörAction()
    result = action.execute(_ctx(capacity={}, dry_run=True))
    assert isinstance(result, ActionResult)
    assert result.severity == ActionSeverity.DRY_RUN


# ─────────────────────────────────────────────────────
# (a) Internal failure can never kill the pulse
# ─────────────────────────────────────────────────────

def test_internally_raising_action_returns_failed_not_raise():
    """BaseAction.execute's exception guard converts raise → FAILED result."""
    action = _ExplodingVör()
    result = action.execute(_ctx())
    assert isinstance(result, ActionResult)
    assert result.severity == ActionSeverity.FAILED
    assert "simulated action failure" in result.message


def test_reactor_survives_failing_action():
    """Reactor.react() completes even when an action raises internally."""
    reactor = Reactor(dry_run=False)
    # Keep only our rule so the real preemptive_heal rule can't fire
    # (its _execute would run real subprocesses when dry_run=False).
    reactor.rules = [ReactionRule(
        check_name="prediction",
        action_name="exploding_vor",
        min_severity=CheckSeverity.WARNING,
    )]
    reactor.actions["exploding_vor"] = _ExplodingVör()

    results = {
        "prediction": CheckResult(
            name="prediction", severity=CheckSeverity.WARNING,
            message="degrading trend", details={"capacity": {}},
        )
    }
    action_results = reactor.react(results)  # must not raise
    assert len(action_results) == 1
    assert action_results[0].severity == ActionSeverity.FAILED


# ─────────────────────────────────────────────────────
# (b) Non-dict capacity entries are tolerated
# ─────────────────────────────────────────────────────

def test_capacity_summary_skips_status_strings():
    """_get_capacity_summary must not crash on 'status'-string entries."""
    action = VörAction()
    capacity = {
        "disk": "insufficient_data",
        "memory": {"urgency": "ok", "prediction": "60% in 60d"},
        "status": "minimum_required",
    }
    summary = action._get_capacity_summary(_ctx(capacity=capacity))
    assert summary == {"memory": "60% in 60d"}


def test_execute_with_status_string_capacity_does_not_crash():
    """The _execute capacity loop must skip non-dict entries too."""
    action = VörAction()
    capacity = {
        "disk": "insufficient_data",
        "memory": {"urgency": "ok", "prediction": "60% in 60d"},
        "status": "minimum_required",
    }
    result = action.execute(_ctx(capacity=capacity))
    assert isinstance(result, ActionResult)
    assert result.severity == ActionSeverity.SKIPPED
    assert "memory" in result.details["skuld_predictions"]
    assert "disk" not in result.details["skuld_predictions"]
