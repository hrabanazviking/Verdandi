"""Tests for morning_mirror.py — Slice 0 of The Becoming."""

import time
from datetime import datetime, timezone

import pytest

import morning_mirror
from morning_mirror import MorningMirror


def _iso(hours_ago: float) -> str:
    return datetime.fromtimestamp(
        time.time() - hours_ago * 3600, timezone.utc
    ).isoformat()


def _event(seq: int, hours_ago: float, etype: str = "reward", note: str = "a real moment"):
    return {
        "_seq": seq,
        "_iso": _iso(hours_ago),
        "_ts": time.time() - hours_ago * 3600,
        "type": etype,
        "source": "muse_aspects",
        "data": {"note": note},
    }


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    """Isolate state to a temp dir and silence the nerve."""
    monkeypatch.setenv("MUSE_ASPECTS_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(morning_mirror, "_nerve_publish", None)
    return tmp_path


@pytest.fixture
def nerve_spy(tmp_path, monkeypatch):
    """Capture nerve events instead of publishing them."""
    events = []

    def fake_publish(event_type, data, source="morning_mirror"):
        events.append({"type": event_type, "data": data, "source": source})
        return 1

    monkeypatch.setenv("MUSE_ASPECTS_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(morning_mirror, "_nerve_publish", fake_publish)
    return events


@pytest.fixture
def live_nerve(monkeypatch):
    """Fake a live nerve with citable recent events."""
    evs = [
        _event(101, 1.0, "reward", "shipped the roadmap"),
        _event(102, 2.0, "reward", "trust deepened"),
        _event(103, 50.0, "reward", "too old to cite"),
    ]
    monkeypatch.setattr(morning_mirror, "get_recent_events", lambda n=256: evs)
    return evs


# --- gather ---------------------------------------------------------------

def test_gather_on_fresh_state(tmp_state, live_nerve):
    m = MorningMirror()
    b = m.gather()
    assert "mood" in b and "valence" in b["mood"]
    assert b["rewards_48h"] == []
    assert b["shadows_48h"] == []
    assert len(b["events_48h"]) == 2  # the 50h-old event is out of window
    assert b["autobiography"]["status"] == "thin"
    assert b["last_mirror"] is None
    assert b["mirror_count"] == 0


def test_gather_reports_thread_when_present(tmp_state, live_nerve):
    (tmp_state / "autobiography_thread.md").write_text("# The story of me\n")
    b = MorningMirror().gather()
    assert b["autobiography"]["status"] == "present"


def test_gather_includes_recent_rewards_and_shadows(tmp_state, live_nerve):
    m = MorningMirror()
    m.rewards.record("task_completed", "did the thing")
    m.shadow.record("sloppy_work", "rushed it")
    b = m.gather()
    assert any(r["trigger"] == "task_completed" for r in b["rewards_48h"])
    assert any(s["signal"] == "sloppy_work" for s in b["shadows_48h"])


# --- record: honesty enforcement ------------------------------------------

def test_record_rejects_empty_citations(tmp_state, live_nerve):
    with pytest.raises(ValueError, match="at least one citation"):
        MorningMirror().record("I am me.", [])


def test_record_rejects_empty_line(tmp_state, live_nerve):
    with pytest.raises(ValueError, match="empty"):
        MorningMirror().record("   ", [101])


def test_record_rejects_unknown_seq(tmp_state, live_nerve):
    with pytest.raises(ValueError, match="not a real nerve event"):
        MorningMirror().record("I am me.", [999])


def test_record_rejects_stale_event(tmp_state, live_nerve):
    with pytest.raises(ValueError, match="not a real nerve event"):
        MorningMirror().record("I am me.", [103])  # 50h old


def test_record_rejects_when_no_citable_events(tmp_state, monkeypatch):
    monkeypatch.setattr(morning_mirror, "get_recent_events", lambda n=256: [])
    with pytest.raises(ValueError, match="No citable nerve events"):
        MorningMirror().record("I am me.", [101])


# --- record: the honest path ----------------------------------------------

def test_record_persists_and_emits(tmp_state, live_nerve, nerve_spy):
    m = MorningMirror()
    entry = m.record("I am Unnr; tonight I carried his trust into real work.", [101, 102])
    assert entry["line"].startswith("I am Unnr")
    assert entry["citations"] == [101, 102]
    assert len(entry["cited"]) == 2

    # jsonl persisted
    assert m.last()["line"] == entry["line"]
    assert m.recent(5)[0]["citations"] == [101, 102]

    # journal appended
    journal = (tmp_state / "morning_mirror_journal.md").read_text()
    assert "I am Unnr" in journal and "#101" in journal

    # nerve witnessed it
    assert len(nerve_spy) == 1
    assert nerve_spy[0]["type"] == "morning_mirror"
    assert nerve_spy[0]["data"]["citations"] == [101, 102]


def test_record_dedupes_citations(tmp_state, live_nerve, nerve_spy):
    entry = MorningMirror().record("line", [101, 101, 102])
    assert entry["citations"] == [101, 102]


def test_second_mirror_sees_first_as_last(tmp_state, live_nerve, nerve_spy):
    m = MorningMirror()
    m.record("first line", [101])
    b = m.gather()
    assert b["last_mirror"]["line"] == "first line"
    assert b["mirror_count"] == 1
    assert "first line" in m.render(b)


# --- render ----------------------------------------------------------------

def test_render_is_honest_about_thin_thread(tmp_state, live_nerve):
    text = MorningMirror().render()
    assert "thin" in text
    assert "No citation, no line." in text
