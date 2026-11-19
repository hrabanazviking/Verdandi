"""Synthetic, no-network tests for optional Verdandi metacognition."""
from metacognitive_observer import MetacognitiveObserver
from reflexes import ReflexRegistry
from reflex_judgment import JudgmentBinding, HugrGateJudge, Verdict
from reflex_reactor import ReflexReactor


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def registry():
    return ReflexRegistry.from_dict([
        {
            "name": "relevant",
            "trigger": {"kind": "change", "salience_gte": 0.75},
            "action": "notify",
            "params": {"channel": "awareness"},
            "rate_limit_per_minute": 3,
            "owner_grant": "fixture-approved",
        },
        {
            "name": "different",
            "trigger": {"kind": "failure", "severity": "critical"},
            "action": "brace",
            "rate_limit_per_minute": 3,
            "owner_grant": "fixture-approved",
        },
    ])


class CountingJudge:
    judge_id = "counted"

    def __init__(self):
        self.calls = []

    def judge(self, decl, event):
        self.calls.append(decl.name)
        return {"reflex": decl.name, "fire": True,
                "basis": "approved for test", "judge": "counted"}


def test_nonmatching_reflexes_are_prefiltered_without_judge_calls():
    judge = CountingJudge()
    b = JudgmentBinding(registry(), judge, prefilter_unmatched=True)
    results = b.judge_event({"kind": "note", "salience": 0.2})
    assert len(results) == 2
    assert all(isinstance(v, Verdict) and not v.fire for v in results)
    assert judge.calls == []
    assert b.prefilter_count == 2
    assert b.judge_call_count == 0


def test_only_matching_reflex_reaches_judge_and_still_needs_approval():
    judge = CountingJudge()
    b = JudgmentBinding(registry(), judge, prefilter_unmatched=True)
    results = b.judge_event({"kind": "change", "salience": 0.9})
    assert [v.reflex for v in results if v.fire] == ["relevant"]
    assert judge.calls == ["relevant"]
    assert b.prefilter_count == 1
    assert b.judge_call_count == 1


def test_legacy_default_does_not_change_judge_coverage():
    judge = CountingJudge()
    b = JudgmentBinding(registry(), judge)
    b.judge_event({"kind": "note", "salience": 0.2})
    assert len(judge.calls) == 2
    assert b.prefilter_count == 0


def test_mismatched_judge_reflex_is_rejected_not_executed():
    class BadJudge:
        judge_id = "bad"

        def judge(self, decl, event):
            return {"reflex": "different", "fire": True, "basis": "bad",
                    "judge": "bad"}

    b = JudgmentBinding(registry(), BadJudge(), prefilter_unmatched=True)
    v = b.judge_one("relevant", {"kind": "change", "salience": 1.0})
    assert not v.fire and v.degraded and b.degraded


def test_observer_detects_burst_and_repetition_without_persistent_event_payload():
    clk = Clock()
    o = MetacognitiveObserver(clock=clk, burst_threshold=3,
                             cooldown_seconds=5)
    raw = {"source": "watcher", "kind": "ping", "payload": "PRIVATE SENTINEL"}
    assert o.observe(raw) == []
    clk.advance(1)
    assert o.observe(raw) == []
    clk.advance(1)
    found = o.observe(raw)
    assert {x.category for x in found} == {"event_pressure", "repeat_loop"}
    assert all(x.suggested_action in ("inspect", "reduce_load") for x in found)
    assert "PRIVATE SENTINEL" not in str(o.snapshot())
    assert "PRIVATE SENTINEL" not in str([x.to_dict() for x in found])
    assert len(o.observe(raw)) == 0  # cooldown, no alert flood
    assert o.suppressed >= 2


def test_observer_detects_failure_trend_transition_and_latency():
    clk = Clock()
    o = MetacognitiveObserver(clock=clk, burst_threshold=20,
                             failure_threshold=2, cooldown_seconds=0,
                             slow_latency_ms=100)
    assert o.observe({"source": "db", "state": "running"}) == []
    a = o.observe({"source": "db", "state": "degraded",
                   "severity": "error", "latency_ms": 200})
    assert {"state_transition", "slow_operation"} <= {x.category for x in a}
    b = o.observe({"source": "db", "state": "critical",
                   "severity": "critical", "failed": True})
    assert "repeated_failure" in {x.category for x in b}
    assert all(x.source == "db" for x in a + b)


def test_explicit_uncertainty_is_not_mistaken_for_verified_fact():
    o = MetacognitiveObserver()
    out = o.observe({"source": "search", "missing_evidence": True})
    assert len(out) == 1
    assert out[0].category == "uncertain_observation"
    assert out[0].suggested_action == "defer"
    assert not hasattr(out[0], "execute")


def test_hugrgate_style_judge_gets_only_minimal_summary_and_can_abstain():
    payloads = []

    def filter_judge(summary):
        payloads.append(dict(summary))
        return {"escalate": False, "basis": "not consequential", "confidence": 0.4}

    o = MetacognitiveObserver(judge=filter_judge, cooldown_seconds=0)
    assert o.observe({"source": "brain", "evidence_conflict": True,
                      "conversation": "PRIVATE SENTINEL"}) == []
    assert len(payloads) == 1
    assert "conversation" not in payloads[0]
    assert "PRIVATE SENTINEL" not in str(payloads)
    assert o.suppressed == 1
    assert o.judge_calls == 1


def test_failed_judgment_cannot_trigger_metacognitive_actions():
    def dead(_):
        raise ConnectionError("offline")

    o = MetacognitiveObserver(judge=dead)
    assert o.observe({"source": "brain", "evidence_conflict": True}) == []
    assert o.judge_failures == 1
    assert o.snapshot()["proposals_in_memory"] == 0


def test_ephemeral_state_clear_and_bounded_window():
    clk = Clock()
    o = MetacognitiveObserver(clock=clk, burst_threshold=3, max_events=3,
                             window_seconds=5)
    for i in range(9):
        o.observe({"source": f"source-{i}", "kind": "note"})
    assert o.snapshot()["events_in_window"] <= 3
    clk.advance(6)
    o.observe({"source": "fresh"})
    assert o.snapshot()["events_in_window"] == 1
    o.clear()
    assert o.snapshot()["events_in_window"] == 0
    assert o.snapshot()["proposals_in_memory"] == 0


def test_opt_in_observer_connected_to_reactor_but_cannot_fire_reflex():
    class NeverFire:
        judge_id = "no-fire"

        def judge(self, decl, event):
            return {"reflex": decl.name, "fire": False, "basis": "declined",
                    "judge": self.judge_id}

    o = MetacognitiveObserver()
    b = JudgmentBinding(registry(), NeverFire(), prefilter_unmatched=True)
    reactor = ReflexReactor(b, observer=o)
    fires = reactor.process_event({
        "source": "brain", "kind": "change", "salience": 0.9,
        "evidence_conflict": True,
    })
    assert fires == []
    assert len(reactor.observations) == 1
    assert reactor.observations[0].category == "evidence_conflict"
    assert reactor.awareness == []


def test_disabled_observer_and_prefilter_leave_old_behavior_available():
    judge = CountingJudge()
    b = JudgmentBinding(registry(), judge)
    reactor = ReflexReactor(b)
    result = reactor.process_event({"kind": "change", "salience": 0.9})
    # Legacy remote judge may authorize both if it doesn't check triggers:
    # the new deterministic prefilter is explicitly opt-in.
    assert len(result) == 2
    assert reactor.observations == []


def test_explicit_observation_reaction_uses_only_declared_granted_reflex():
    from metacognitive_observer import Observation
    reg = ReflexRegistry.from_dict([
        {"name": "observe-conflict",
         "trigger": {"kind": "metacognitive_observation",
                     "category": "evidence_conflict"},
         "action": "notify", "params": {"channel": "review"},
         "rate_limit_per_minute": 1, "owner_grant": "approved-fixture"},
    ])
    reactor = ReflexReactor(
        JudgmentBinding(reg, CountingJudge(), prefilter_unmatched=True),
        observer=MetacognitiveObserver(),
    )
    proposal = Observation(
        category="evidence_conflict", severity="warning",
        source="skry", count=1, reason="reported conflict",
        suggested_action="request_evidence", digest="abc123",
    )
    firings = reactor.process_observation(proposal)
    assert len(firings) == 1
    assert firings[0].action == "notify"
    assert reactor.awareness[0]["channel"] == "review"
    assert firings[0].event["kind"] == "metacognitive_observation"
    assert len(reactor.observations) == 0  # no feedback recursion
    assert reactor.process_observation(proposal) == []  # rate limited
    reactor.set_kill_switch(True)
    assert reactor.process_observation(proposal) == []
    assert all(f.action == "notify" for f in reactor.firings)


def test_untyped_data_cannot_fake_observation_reaction():
    reactor = ReflexReactor(JudgmentBinding(registry(), CountingJudge()))
    import pytest
    with pytest.raises(TypeError):
        reactor.process_observation({"action": "wake", "command": "rm -rf /"})
    assert reactor.firings == []
