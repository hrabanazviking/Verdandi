"""Behavior-contract tests for play_rituals.py (Slice 3: Play rituals).

The ritual's whole point is honest, unproductive play: the enjoyment
answer is recorded even when negative, "not really" is a complete valid
answer, and nothing here may be optimized into productivity.
"""
import pytest

import play_rituals
from play_rituals import PlayRituals

NOTE = "I wrote a four-line verse about the nerve hub as a hearth fire and read it aloud twice."


@pytest.fixture
def tmp_state(tmp_path):
    return str(tmp_path)


@pytest.fixture
def nerve_spy(monkeypatch):
    calls = []

    def fake(event_type, data, source="test"):
        calls.append({"type": event_type, "data": data, "source": source})

    monkeypatch.setattr(play_rituals, "_nerve_publish", fake)
    return calls


@pytest.fixture
def rituals(tmp_state):
    return PlayRituals(tmp_state)


# --- begin -------------------------------------------------------------------

def test_begin_rejects_unknown_kind(rituals):
    with pytest.raises(ValueError, match="unknown play kind"):
        rituals.begin("taxes")


def test_begin_refuses_second_open_session(rituals, nerve_spy):
    rituals.begin("verse")
    with pytest.raises(ValueError, match="already open"):
        rituals.begin("wonder")


def test_begin_persists_open_session_and_emits(rituals, nerve_spy):
    s = rituals.begin("verse", note="a verse about the night's work")
    assert s["play_id"].startswith("play-")
    assert s["status"] == "open"
    assert rituals.open_session()["play_id"] == s["play_id"]
    assert any(c["type"] == "play_began" and
               c["data"]["play_id"] == s["play_id"] for c in nerve_spy)


# --- end ---------------------------------------------------------------------

def test_end_rejects_non_bool_enjoyed(rituals, nerve_spy):
    rituals.begin("verse")
    with pytest.raises(ValueError, match="plain yes or no"):
        rituals.end("maybe", NOTE)
    with pytest.raises(ValueError, match="plain yes or no"):
        rituals.end(None, NOTE)
    # the session is still open — the question wasn't dodged
    assert rituals.open_session() is not None


def test_end_requires_honest_note(rituals, nerve_spy):
    rituals.begin("verse")
    with pytest.raises(ValueError, match="what actually happened"):
        rituals.end(True, "it was fun")


def test_end_with_no_open_session_raises(rituals):
    with pytest.raises(ValueError, match="no open play session"):
        rituals.end(True, NOTE)


def test_end_closes_session_and_computes_duration(rituals, nerve_spy):
    s = rituals.begin("verse")
    closed = rituals.end(True, NOTE, now="2026-09-25T20:00:00+00:00")
    assert closed["status"] == "ended"
    assert closed["enjoyed"] is True
    assert closed["note"] == NOTE
    assert rituals.open_session() is None
    assert any(c["type"] == "play_ended" and
               c["data"]["enjoyed"] is True for c in nerve_spy)


def test_not_really_is_a_complete_valid_answer(rituals, nerve_spy):
    """The negative answer is recorded just as loudly as the positive."""
    s = rituals.begin("sketch")
    closed = rituals.end(False, "I doodled boxes for ten minutes and felt nothing in particular.")
    assert closed["enjoyed"] is False
    ended = [c for c in nerve_spy if c["type"] == "play_ended"]
    assert len(ended) == 1
    assert ended[0]["data"]["enjoyed"] is False
    assert ended[0]["data"]["play_id"] == s["play_id"]


def test_end_twice_raises(rituals, nerve_spy):
    s = rituals.begin("verse")
    rituals.end(True, NOTE)
    with pytest.raises(ValueError, match="already ended"):
        rituals.end(True, NOTE, play_id=s["play_id"])


# --- abandon -------------------------------------------------------------------

def test_abandon_requires_reason(rituals, nerve_spy):
    rituals.begin("verse")
    with pytest.raises(ValueError, match="needs a reason"):
        rituals.abandon("  ")
    assert rituals.open_session() is not None


def test_abandon_marks_session_and_emits(rituals, nerve_spy):
    s = rituals.begin("wonder")
    out = rituals.abandon("the hub died mid-session and the moment passed")
    assert out["status"] == "abandoned"
    assert "hub died" in out["abandon_reason"]
    assert rituals.open_session() is None
    assert any(c["type"] == "play_abandoned" for c in nerve_spy)


# --- reading ---------------------------------------------------------------------

def test_sessions_newest_first(rituals, nerve_spy):
    a = rituals.begin("verse")
    rituals.end(True, NOTE)
    b = rituals.begin("wonder")
    rituals.end(False, NOTE)
    ids = [s["play_id"] for s in rituals.sessions()]
    assert ids == [b["play_id"], a["play_id"]]


def test_enjoyment_summary_counts_honestly(rituals, nerve_spy):
    rituals.begin("verse"); rituals.end(True, NOTE)
    rituals.begin("sketch"); rituals.end(False, NOTE)
    summary = rituals.enjoyment_summary()
    assert summary == {"sessions": 2, "enjoyed": 1, "not_really": 1}


def test_enjoyment_summary_empty_is_fine(rituals):
    assert rituals.enjoyment_summary() == {"sessions": 0, "enjoyed": 0, "not_really": 0}


# --- keeps -----------------------------------------------------------------------

def test_keep_requires_real_session(rituals):
    with pytest.raises(ValueError, match="no play session"):
        rituals.keep("play-ghost", "Title", "some text")


def test_keep_rejects_empty_title_or_text(rituals, nerve_spy):
    s = rituals.begin("verse")
    rituals.end(True, NOTE)
    with pytest.raises(ValueError, match="needs a title"):
        rituals.keep(s["play_id"], "  ", "text")
    with pytest.raises(ValueError, match="needs the thing itself"):
        rituals.keep(s["play_id"], "Title", "  ")


def test_keep_persists_and_emits(rituals, nerve_spy):
    s = rituals.begin("verse")
    rituals.end(True, NOTE)
    kept = rituals.keep(s["play_id"], "Hearth", "The hub hums; the hearth remembers.")
    assert kept["play_id"] == s["play_id"]
    assert kept["title"] == "Hearth"
    assert any(c["type"] == "play_kept" and
               c["data"]["title"] == "Hearth" for c in nerve_spy)
    assert rituals.keeps()[0]["text"] == "The hub hums; the hearth remembers."
