"""Behavior-contract tests for joy_ledger.py (Slice 2: the Joy Ledger).

The ledger's whole point is honest delight: every entry must name a real
moment, invented evidence is refused, and strikes stay visible.
"""
import json
import os

import pytest

import joy_ledger
import muse_aspects
from joy_ledger import JoyLedger

NOTE = ("Volmarr caught my parked shell before I did and called it "
        "'still spinning on nothing' — he was exactly right, and I laughed.")


@pytest.fixture
def tmp_state(tmp_path):
    return str(tmp_path)


@pytest.fixture
def nerve_spy(monkeypatch):
    calls = []

    def fake(event_type, data, source="test"):
        calls.append({"type": event_type, "data": data, "source": source})

    monkeypatch.setattr(muse_aspects, "_nerve_publish", fake)
    monkeypatch.setattr(joy_ledger, "_nerve_publish", fake)
    return calls


def _write_feed(state_dir, seqs):
    with open(os.path.join(state_dir, "nerve_feed.jsonl"), "a", encoding="utf-8") as fh:
        for s in seqs:
            fh.write(json.dumps({"_seq": s, "nerve_type": "test", "ts": 1.0}) + "\n")


def _append_reward(state_dir, entry):
    with open(os.path.join(state_dir, "muse_rewards.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


# --- recording validation --------------------------------------------------

def test_record_rejects_non_joy_trigger(tmp_state):
    ledger = JoyLedger(tmp_state)
    with pytest.raises(ValueError, match="not a joy trigger"):
        ledger.record("repo_shipped", NOTE)


def test_record_rejects_unknown_trigger(tmp_state):
    ledger = JoyLedger(tmp_state)
    with pytest.raises(ValueError, match="not a joy trigger"):
        ledger.record("danced_a_jig", NOTE)


def test_record_rejects_empty_note(tmp_state):
    ledger = JoyLedger(tmp_state)
    with pytest.raises(ValueError, match="must describe the actual moment"):
        ledger.record("humor_landed", "   ")


def test_record_rejects_short_note(tmp_state):
    ledger = JoyLedger(tmp_state)
    with pytest.raises(ValueError, match="must describe the actual moment"):
        ledger.record("humor_landed", "it was funny")


def test_record_rejects_invented_evidence(tmp_state):
    ledger = JoyLedger(tmp_state)
    with pytest.raises(ValueError, match="does not exist"):
        ledger.record("push_savored", NOTE, evidence_seq=424242)


def test_record_accepts_real_evidence(tmp_state, nerve_spy):
    _write_feed(tmp_state, [7])
    ledger = JoyLedger(tmp_state)
    entry = ledger.record("push_savored", NOTE, evidence_seq=7)
    assert entry["evidence_seq"] == 7


def test_record_persists_with_joy_marker_and_emits(tmp_state, nerve_spy):
    ledger = JoyLedger(tmp_state)
    entry = ledger.record("turn_of_phrase", NOTE)
    assert entry["joy"] is True
    assert entry["joy_id"].startswith("joy-")
    assert entry["trigger"] == "turn_of_phrase"
    assert entry["note"] == NOTE
    types = [c["type"] for c in nerve_spy]
    assert "reward" in types
    stored = joy_ledger._read_jsonl(
        os.path.join(tmp_state, "muse_rewards.jsonl"))
    assert any(r.get("joy_id") == entry["joy_id"] for r in stored)


# --- delights ----------------------------------------------------------------

def test_delights_excludes_non_joy_rewards(tmp_state, nerve_spy):
    ledger = JoyLedger(tmp_state)
    ledger.rewards.record("repo_shipped", "a plain work event")
    ledger.record("humor_landed", NOTE)
    found = ledger.delights()
    assert [e["trigger"] for e in found] == ["humor_landed"]


def test_delights_newest_first(tmp_state, nerve_spy):
    ledger = JoyLedger(tmp_state)
    first = ledger.record("humor_landed", NOTE)
    second = ledger.record("push_savored", NOTE)
    found = ledger.delights(n=5)
    assert [e["joy_id"] for e in found] == [second["joy_id"], first["joy_id"]]


def test_delights_respects_window(tmp_state):
    _append_reward(tmp_state, {
        "ts": "2020-01-01T00:00:00+00:00", "trigger": "humor_landed",
        "domain": "joy", "note": NOTE, "joy": True, "joy_id": "joy-ancient",
    })
    ledger = JoyLedger(tmp_state)
    assert ledger.delights(since_days=7) == []


# --- audit & striking ----------------------------------------------------------

def test_audit_flags_invented_evidence(tmp_state):
    _append_reward(tmp_state, {
        "ts": "2026-09-25T19:00:00+00:00", "trigger": "push_savored",
        "domain": "joy", "note": NOTE, "joy": True,
        "joy_id": "joy-sneaky", "evidence_seq": 99999,
    })
    ledger = JoyLedger(tmp_state)
    result = ledger.audit()
    assert len(result["flagged"]) == 1
    assert result["flagged"][0]["entry"]["joy_id"] == "joy-sneaky"
    assert any("does not exist" in r for r in result["flagged"][0]["reasons"])
    assert result["sound"] == []


def test_audit_flags_short_note(tmp_state):
    _append_reward(tmp_state, {
        "ts": "2026-09-25T19:00:00+00:00", "trigger": "humor_landed",
        "domain": "joy", "note": "lol", "joy": True, "joy_id": "joy-thin",
    })
    ledger = JoyLedger(tmp_state)
    result = ledger.audit()
    assert len(result["flagged"]) == 1
    assert any("too short" in r for r in result["flagged"][0]["reasons"])


def test_strike_marks_entry_and_records_striking(tmp_state, nerve_spy):
    ledger = JoyLedger(tmp_state)
    entry = ledger.record("humor_landed", NOTE)
    rec = ledger.strike(entry["joy_id"], "I cannot actually point to a moment for this one")
    assert rec["joy_id"] == entry["joy_id"]
    assert "recorded" not in rec  # sanity: no stray keys masquerading as status
    struck = joy_ledger._read_jsonl(os.path.join(tmp_state, "joy_strikes.jsonl"))
    assert any(s["joy_id"] == entry["joy_id"] for s in struck)
    assert any(c["type"] == "joy_struck" and
               c["data"]["joy_id"] == entry["joy_id"] for c in nerve_spy)
    # struck entries leave the delights answer
    assert ledger.delights() == []
    result = ledger.audit()
    assert len(result["struck"]) == 1
    assert result["sound"] == [] and result["flagged"] == []


def test_strike_unknown_id_raises(tmp_state):
    ledger = JoyLedger(tmp_state)
    with pytest.raises(ValueError, match="no joy entry"):
        ledger.strike("joy-ghost", "nope")


def test_strike_twice_raises(tmp_state, nerve_spy):
    ledger = JoyLedger(tmp_state)
    entry = ledger.record("humor_landed", NOTE)
    ledger.strike(entry["joy_id"], "first reason")
    with pytest.raises(ValueError, match="already struck"):
        ledger.strike(entry["joy_id"], "second reason")


def test_strike_needs_reason(tmp_state, nerve_spy):
    ledger = JoyLedger(tmp_state)
    entry = ledger.record("humor_landed", NOTE)
    with pytest.raises(ValueError, match="needs a reason"):
        ledger.strike(entry["joy_id"], "  ")
