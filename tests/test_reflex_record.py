import json
from pathlib import Path
from reflexes import ReflexRegistry
from reflex_judgment import FixtureJudge, JudgmentBinding
from reflex_reactor import ReflexReactor
from reflex_record import FiringRecord, event_digest

FIX = Path(__file__).parent / "fixtures"
EVENTS = json.loads((FIX / "reflex_event_stream_fixture.json").read_text())["events"]
EXPECTED = ["spike-notify", "threat-brace", "noisy-shed", "stalled-wake", "alert-speak"]


def run(tmp_path):
    reg = ReflexRegistry.load(FIX / "reflex_first_set_fixture.json")
    rec = FiringRecord(tmp_path / "firing_record.jsonl")
    r = ReflexReactor(JudgmentBinding(reg, FixtureJudge()), record=rec)
    firings = r.process_stream(EVENTS)
    return rec, firings


def test_fixture_run_record_complete_one_entry_per_firing(tmp_path):
    rec, firings = run(tmp_path)
    entries = rec.firings()
    assert len(firings) == 5
    assert len(entries) == 5
    assert [e["reflex"] for e in entries] == EXPECTED
    for e, f in zip(entries, firings):
        assert e["event_digest"] == event_digest(f.event)
        assert e["event"] == f.event
        assert e["basis"] == f.basis and "matched" in e["basis"]
        assert e["judge"] == f.judge
        assert e["action"] == f.action
        assert e["result"] == f.effect
        assert e["latency_ms"] == f.latency_ms
        assert e["fire"] is True and e["kind"] == "firing"


def test_no_fire_above_salience_floor_recorded_below_not(tmp_path):
    rec, _ = run(tmp_path)
    no_fires = [e for e in rec.entries() if e["kind"] == "no_fire"]
    assert no_fires, "expected judged no-fires above the floor to be recorded"
    for e in no_fires:
        vals = [e["event"].get(k) for k in ("salience", "threat", "noise")]
        assert max(v for v in vals if isinstance(v, (int, float))) >= 0.5
        assert e["fire"] is False and e["basis"] and e["result"] is None
    # The low-salience event (0.1 / 0.3) must produce no no_fire entries.
    low_digests = {event_digest(EVENTS[1]), event_digest(EVENTS[10])}
    assert not [e for e in no_fires if e["event_digest"] in low_digests]


def test_record_survives_restart_and_appends(tmp_path):
    rec, _ = run(tmp_path)
    before = rec.entries()
    rec2 = FiringRecord(tmp_path / "firing_record.jsonl")
    assert rec2.entries() == before
    assert rec2.review()["firings"] == 5
    reg = ReflexRegistry.load(FIX / "reflex_first_set_fixture.json")
    r2 = ReflexReactor(JudgmentBinding(reg, FixtureJudge()), record=rec2)
    r2.process_event(EVENTS[0])
    after = rec2.entries()
    assert len(after) > len(before)
    assert after[:len(before)] == before  # append-only: prefix unchanged
    assert len(rec2.firings()) == 6
    assert after[-1]["seq"] > before[-1]["seq"]


def test_review_and_for_reflex(tmp_path):
    rec, _ = run(tmp_path)
    rev = rec.review()
    assert rev["firings"] == 5 and rev["total"] >= 5
    assert len(rec.for_reflex("spike-notify")) >= 1
    assert rec.for_reflex("spike-notify")[0]["action"] == "notify"
