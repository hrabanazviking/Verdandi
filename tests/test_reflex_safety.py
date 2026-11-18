import json
from pathlib import Path
from reflexes import ReflexRegistry
from reflex_judgment import FixtureJudge, JudgmentBinding
from reflex_reactor import ReflexReactor

FIX = Path(__file__).parent / "fixtures"
SPIKE = {"feed": "wyrd", "salience": 0.9}
ALERT = {"kind": "alert"}

class FakeClock:
    def __init__(self):
        self.now = 1000.0
    def __call__(self):
        return self.now
    def advance(self, seconds):
        self.now += seconds

def make(clock=None, handlers=None):
    reg = ReflexRegistry.load(FIX / "reflex_first_set_fixture.json")
    return ReflexReactor(JudgmentBinding(reg, FixtureJudge()), clock=clock, handlers=handlers)

def test_rate_limit_blocks_flood_and_window_recovers():
    clock = FakeClock()
    r = make(clock=clock)
    # spike-notify rate_limit_per_minute is 6 in the fixture
    fired = []
    for _ in range(10):
        fired.extend(r.process_event(dict(SPIKE)))
    assert len(fired) == 6
    assert len(r.firings) == 6
    assert sum(1 for b in r.blocked if b["reason"] == "rate_limit") == 4
    clock.advance(61)
    assert len(r.process_event(dict(SPIKE))) == 1

def test_quiet_state_blocks_all_firing_and_resumes():
    r = make()
    r.set_quiet(True)
    assert r.process_event(dict(SPIKE)) == []
    assert r.process_event(dict(ALERT)) == []
    assert r.firings == [] and r.awareness == [] and r.spoken == []
    assert {b["reason"] for b in r.blocked} == {"quiet_state"}
    r.set_quiet(False)
    assert len(r.process_event(dict(SPIKE))) == 1

def test_kill_switch_effective_immediately():
    r = make()
    assert len(r.process_event(dict(SPIKE))) == 1
    r.set_kill_switch(True)
    assert r.process_event(dict(SPIKE)) == []
    assert r.process_event(dict(ALERT)) == []
    assert {b["reason"] for b in r.blocked} == {"kill_switch"}
    r.set_kill_switch(False)
    assert len(r.process_event(dict(ALERT))) == 1

def test_per_reflex_disable_blocks_only_that_reflex():
    r = make()
    r.disable_reflex("spike-notify")
    assert r.process_event(dict(SPIKE)) == []
    assert len(r.process_event(dict(ALERT))) == 1
    assert r.blocked[0]["reflex"] == "spike-notify" and r.blocked[0]["reason"] == "disabled"
    r.enable_reflex("spike-notify")
    assert len(r.process_event(dict(SPIKE))) == 1

def test_erroring_action_self_disables_after_two_consecutive_and_reports():
    calls = {"n": 0}
    def boom(decl, event):
        calls["n"] += 1
        raise RuntimeError("boom")
    r = make(handlers={"notify": boom})
    assert r.process_event(dict(SPIKE)) == []
    assert "spike-notify" not in r.disabled
    assert r.process_event(dict(SPIKE)) == []
    assert "spike-notify" in r.disabled
    kinds = [x["kind"] for x in r.safety_reports]
    assert kinds.count("reflex_error") == 2 and "reflex_self_disabled" in kinds
    # third attempt: blocked as disabled, handler not retried
    assert r.process_event(dict(SPIKE)) == []
    assert calls["n"] == 2
    # other reflexes still fire
    assert len(r.process_event(dict(ALERT))) == 1

def test_single_error_then_success_does_not_disable():
    state = {"fail": True}
    def flaky(decl, event):
        if state["fail"]:
            state["fail"] = False
            raise RuntimeError("once")
        return {"ok": True}
    r = make(handlers={"notify": flaky})
    assert r.process_event(dict(SPIKE)) == []
    assert len(r.process_event(dict(SPIKE))) == 1
    assert "spike-notify" not in r.disabled
    assert len(r.process_event(dict(SPIKE))) == 1
