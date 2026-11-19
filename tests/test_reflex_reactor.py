import json
from pathlib import Path
import pytest
from reflexes import ReflexRegistry
from reflex_judgment import FixtureJudge, JudgmentBinding
from reflex_reactor import ReflexReactor, UnknownActionError

FIX = Path(__file__).parent / "fixtures"
EVENTS = json.loads((FIX / "reflex_event_stream_fixture.json").read_text())["events"]
EXPECTED = ["spike-notify", "threat-brace", "noisy-shed", "stalled-wake", "alert-speak"]

def reactor():
    reg = ReflexRegistry.load(FIX / "reflex_first_set_fixture.json")
    return ReflexReactor(JudgmentBinding(reg, FixtureJudge()))

def test_stream_fires_each_reflex_exactly_once_on_its_pattern():
    r = reactor(); firings = r.process_stream(EVENTS)
    assert [f.reflex for f in firings] == EXPECTED
    assert [f.action for f in firings] == ["notify", "brace", "shed", "wake", "speak"]

def test_effects_land():
    r = reactor(); r.process_stream(EVENTS)
    assert len(r.awareness) == 1 and r.awareness[0]["channel"] == "awareness"
    assert r.watch_levels == {"ops": "high"}
    assert r.shed_sources == {"chatter": 60}
    assert r.started == ["heartbeat"]
    assert len(r.spoken) == 1 and r.spoken[0]["channel"] == "hall" and "alert" in r.spoken[0]["phrase"]

def test_non_matching_events_fire_nothing():
    r = reactor()
    for e in [EVENTS[1], EVENTS[3], EVENTS[5], EVENTS[7], EVENTS[9], EVENTS[10]]:
        assert r.process_event(e) == []
    assert r.firings == []

def test_latency_measured_per_reflex_and_recorded():
    r = reactor(); firings = r.process_stream(EVENTS)
    assert set(r.latencies) == set(EXPECTED)
    for f in firings:
        assert isinstance(f.latency_ms, float) and f.latency_ms >= 0
        assert f.to_dict()["latency_ms"] == f.latency_ms
        assert f.basis and "matched" in f.basis

def test_no_fire_when_judge_says_no_despite_trigger_like_event():
    r = reactor()
    assert r.process_event({"feed": "other", "salience": 0.99}) == []

def test_unknown_action_rejected():
    reg = ReflexRegistry.from_dict([{"name": "x-fly", "trigger": {"a": 1}, "action": "fly", "rate_limit_per_minute": 1, "owner_grant": "g"}])
    with pytest.raises(UnknownActionError):
        ReflexReactor(JudgmentBinding(reg, FixtureJudge()))
