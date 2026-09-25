"""Behavior-contract tests for shadow_arcs.py (Slice 7: Shadow integration arcs).

The arc's whole point is metabolized failure: the stage machine cannot
be skipped, and an arc closes only on evidence — observed subsequent
behavior proving the repair held, never the apology.
"""
import json
import os

import pytest

import shadow_arcs
from shadow_arcs import ShadowArcs

SIGNAL_NOTE = ("The nerve watchdog checked the PID file instead of pinging the socket; "
               "the hub died and the outage went unnoticed until I stumbled on it.")
ACK_NOTE = "My liveness check was a glance, not a ping. That one is on me, no deflection."
REPAIR_NOTE = "Rewrote the watchdog to check the Responsive line and restart when unresponsive."
VERIFY_NOTE = ("The proof is subsequent behavior: the hub stays responsive to socket pings "
               "and the 30-minute checks see a live hub.")
EVIDENCE = ("After the restart the hub answered every status ping, survived its parent "
            "shell's death and reparented cleanly, and a sweep shows no parked launcher "
            "shells. The hardened watchdog is in place and the repair held.")


@pytest.fixture
def tmp_state(tmp_path):
    return str(tmp_path)


@pytest.fixture
def nerve_spy(monkeypatch):
    calls = []

    def fake(event_type, data, source="test"):
        calls.append({"type": event_type, "data": data, "source": source})

    monkeypatch.setattr(shadow_arcs, "_nerve_publish", fake)
    return calls


@pytest.fixture
def sa(tmp_state):
    return ShadowArcs(tmp_state)


def _full_arc(sa, signal="sloppy_work"):
    a = sa.open_arc(signal, SIGNAL_NOTE)
    sa.acknowledge(a["arc_id"], ACK_NOTE)
    sa.add_repair(a["arc_id"], REPAIR_NOTE)
    sa.begin_verification(a["arc_id"], VERIFY_NOTE)
    return sa.close(a["arc_id"], EVIDENCE)


# --- opening ---------------------------------------------------------------

def test_open_rejects_unknown_signal(sa):
    with pytest.raises(ValueError, match="unknown shadow signal"):
        sa.open_arc("vibes_were_off", SIGNAL_NOTE)


def test_open_rejects_short_note(sa):
    with pytest.raises(ValueError, match="at least 24 characters"):
        sa.open_arc("sloppy_work", "my bad")


def test_open_persists_and_emits(sa, nerve_spy):
    a = sa.open_arc("sloppy_work", SIGNAL_NOTE)
    assert a["arc_id"].startswith("arc-")
    assert a["status"] == "opened"
    assert a["signal"] == "sloppy_work"
    assert sa.get(a["arc_id"])["signal_note"] == SIGNAL_NOTE
    assert any(c["type"] == "arc_opened" and
               c["data"]["arc_id"] == a["arc_id"] for c in nerve_spy)


# --- the stage machine cannot be skipped -------------------------------------

def test_acknowledge_requires_opened(sa, nerve_spy):
    a = sa.open_arc("sloppy_work", SIGNAL_NOTE)
    sa.acknowledge(a["arc_id"], ACK_NOTE)
    with pytest.raises(ValueError, match="right after the signal"):
        sa.acknowledge(a["arc_id"], ACK_NOTE)


def test_acknowledge_rejects_short_note(sa):
    a = sa.open_arc("sloppy_work", SIGNAL_NOTE)
    with pytest.raises(ValueError, match="at least 24 characters"):
        sa.acknowledge(a["arc_id"], "sorry")


def test_repair_requires_acknowledgment(sa):
    a = sa.open_arc("sloppy_work", SIGNAL_NOTE)
    with pytest.raises(ValueError, match="acknowledge the signal before repairing"):
        sa.add_repair(a["arc_id"], REPAIR_NOTE)


def test_verify_requires_repairing_status(sa):
    a = sa.open_arc("sloppy_work", SIGNAL_NOTE)
    sa.acknowledge(a["arc_id"], ACK_NOTE)
    with pytest.raises(ValueError, match="verification follows repair"):
        sa.begin_verification(a["arc_id"], VERIFY_NOTE)


def test_verify_requires_a_recorded_repair(sa, tmp_state):
    a = sa.open_arc("sloppy_work", SIGNAL_NOTE)
    sa.acknowledge(a["arc_id"], ACK_NOTE)
    # force the corner: status repairing but repairs list empty (hand-edited state)
    path = os.path.join(tmp_state, "shadow_arcs.json")
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    data[a["arc_id"]]["status"] = "repairing"
    data[a["arc_id"]]["repairs"] = []
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    with pytest.raises(ValueError, match="no recorded repairs"):
        sa.begin_verification(a["arc_id"], VERIFY_NOTE)


def test_close_requires_verifying(sa):
    a = sa.open_arc("sloppy_work", SIGNAL_NOTE)
    sa.acknowledge(a["arc_id"], ACK_NOTE)
    sa.add_repair(a["arc_id"], REPAIR_NOTE)
    with pytest.raises(ValueError, match="closes from verification, on evidence"):
        sa.close(a["arc_id"], EVIDENCE)


def test_close_rejects_thin_evidence(sa):
    a = sa.open_arc("sloppy_work", SIGNAL_NOTE)
    sa.acknowledge(a["arc_id"], ACK_NOTE)
    sa.add_repair(a["arc_id"], REPAIR_NOTE)
    sa.begin_verification(a["arc_id"], VERIFY_NOTE)
    with pytest.raises(ValueError, match="at least 48 characters"):
        sa.close(a["arc_id"], "it seems fine now")


# --- full arc -----------------------------------------------------------------

def test_full_arc_closes_on_evidence(sa, nerve_spy):
    a = _full_arc(sa)
    assert a["status"] == "closed"
    assert a["closing_evidence"] == EVIDENCE
    assert a["closed_at"]
    assert [h["stage"] for h in a["history"]] == [
        "opened", "acknowledged", "repairing", "verifying", "closed"]
    closed = [c for c in nerve_spy if c["type"] == "arc_closed"]
    assert len(closed) == 1
    assert closed[0]["data"]["evidence"] == EVIDENCE
    # closed arcs leave the open list
    assert sa.open_arcs() == []


def test_reopen_requires_closed(sa):
    a = sa.open_arc("sloppy_work", SIGNAL_NOTE)
    with pytest.raises(ValueError, match="only a closed arc can be reopened"):
        sa.reopen(a["arc_id"], "it broke again")


def test_reopen_returns_to_repairing_and_counts(sa, nerve_spy):
    a = _full_arc(sa)
    re = sa.reopen(a["arc_id"], "the hub went quiet again a week later — the lesson didn't hold")
    assert re["status"] == "repairing"
    assert re["reopen_count"] == 1
    assert any(c["type"] == "arc_reopened" and
               c["data"]["reopen_count"] == 1 for c in nerve_spy)
    # the earlier closure stays in the history — scars visible
    stages = [h["stage"] for h in re["history"]]
    assert "closed" in stages and stages[-1] == "reopened"
    # and the arc can be walked to closure again
    sa.add_repair(a["arc_id"], "dug deeper: the socket path itself was the flake, not the check")
    sa.begin_verification(a["arc_id"], VERIFY_NOTE)
    again = sa.close(a["arc_id"], EVIDENCE)
    assert again["status"] == "closed"
    assert again["reopen_count"] == 1


# --- reading --------------------------------------------------------------------

def test_arcs_filter_by_status(sa, nerve_spy):
    a = sa.open_arc("sloppy_work", SIGNAL_NOTE)
    _full_arc(sa, signal="silent_too_long")
    assert [x["arc_id"] for x in sa.arcs(status="opened")] == [a["arc_id"]]
    assert len(sa.arcs(status="closed")) == 1
    with pytest.raises(ValueError, match="unknown status"):
        sa.arcs(status="napping")


def test_narrate_tells_the_story(sa):
    a = _full_arc(sa)
    story = sa.narrate(a["arc_id"])
    assert "sloppy_work" in story
    assert "closed" in story
    assert ACK_NOTE[:20] in story
