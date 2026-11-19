import json
from pathlib import Path
from reflexes import ReflexRegistry
from reflex_judgment import FixtureJudge, JudgmentBinding
from reflex_reactor import ReflexReactor
from reflex_record import FiringRecord

FIX = Path(__file__).parent / "fixtures"

def test_tviheimr_fixture_consumer_sees_reflex_fire_while_feed_flows(tmp_path):
    feed = tmp_path / "nerve_feed.jsonl"
    events = [
        {"feed": "wyrd", "salience": 0.3, "kind": "note"},
        {"feed": "wyrd", "salience": 0.9, "kind": "spike"},
        {"feed": "ops", "salience": 0.2, "kind": "note"},
    ]
    with feed.open("w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")
    record = FiringRecord(tmp_path / "firing_record.jsonl")
    reg = ReflexRegistry.load(FIX / "reflex_first_set_fixture.json")
    reactor = ReflexReactor(JudgmentBinding(reg, FixtureJudge()), record=record)
    seen = []
    firings = []
    # Fixture consumer: reads the feed line by line as it flows,
    # handing each event to the reactor, never stopping for reflexes.
    with feed.open() as fh:
        for line in fh:
            event = json.loads(line)
            seen.append(event)
            firings.extend(reactor.process_event(event))
    assert seen == events  # awareness feed flowed uninterrupted, in order
    assert [f.reflex for f in firings] == ["spike-notify"]
    assert firings[0].latency_ms >= 0 and "matched" in firings[0].basis
    entries = record.firings()
    assert len(entries) == 1
    assert entries[0]["reflex"] == "spike-notify" and entries[0]["latency_ms"] == firings[0].latency_ms
    assert len(reactor.awareness) == 1
