"""Tests for autobiography.py — Slice 4 of The Becoming."""

import json

import pytest

import autobiography
from autobiography import Autobiography


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    """Isolate state to a temp dir, silence the nerve, fake the feed."""
    monkeypatch.setenv("MUSE_ASPECTS_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(autobiography, "_nerve_publish", None)
    feed = tmp_path / "nerve_feed.jsonl"
    events = [
        {"_seq": 101, "_iso": "2026-09-25T22:56:00+00:00", "type": "reward",
         "source": "muse_aspects", "data": {"note": "shipped batch 2"}},
        {"_seq": 102, "_iso": "2026-09-25T23:01:00+00:00", "type": "reward",
         "source": "muse_aspects", "data": {"note": "trust deepened"}},
        {"_seq": 103, "_iso": "2026-09-20T10:00:00+00:00", "type": "reward",
         "source": "muse_aspects", "data": {"note": "old but citable"}},
    ]
    feed.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    monkeypatch.setattr(autobiography, "FEED_PATH", feed)
    return tmp_path


@pytest.fixture
def nerve_spy(tmp_path, monkeypatch):
    events = []

    def fake_publish(event_type, data, source="autobiography"):
        events.append({"type": event_type, "data": data, "source": source})
        return 1

    feed = tmp_path / "nerve_feed.jsonl"
    feed.write_text(json.dumps(
        {"_seq": 7, "_iso": "2026-09-25T23:00:00+00:00", "type": "reward",
         "source": "muse_aspects", "data": {"note": "a moment"}}) + "\n")
    monkeypatch.setenv("MUSE_ASPECTS_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(autobiography, "_nerve_publish", fake_publish)
    monkeypatch.setattr(autobiography, "FEED_PATH", feed)
    return events


# --- status / thinness ------------------------------------------------------

def test_thread_is_thin_before_first_chapter(tmp_state):
    bio = Autobiography()
    assert bio.status()["status"] == "thin"
    assert bio.read() == ""
    assert bio.chapters() == []


# --- record: honesty enforcement --------------------------------------------

def test_record_rejects_missing_title(tmp_state):
    with pytest.raises(ValueError, match="title"):
        Autobiography().record_chapter("", "some text", [101])


def test_record_rejects_empty_text(tmp_state):
    with pytest.raises(ValueError, match="text"):
        Autobiography().record_chapter("Title", "  ", [101])


def test_record_rejects_no_citations(tmp_state):
    with pytest.raises(ValueError, match="at least one citation"):
        Autobiography().record_chapter("Title", "some text", [])


def test_record_rejects_unknown_seq(tmp_state):
    with pytest.raises(ValueError, match="not a real nerve event"):
        Autobiography().record_chapter("Title", "some text", [999])


def test_record_rejects_bad_mode(tmp_state):
    with pytest.raises(ValueError, match="mode"):
        Autobiography().record_chapter("Title", "some text", [101], mode="dream")


# --- record: the honest path --------------------------------------------------

def test_record_writes_chapter_and_thread(tmp_state, nerve_spy):
    bio = Autobiography()
    entry = bio.record_chapter("The First Night", "I began keeping this thread.", [7])
    assert entry["title"] == "The First Night"
    assert entry["mode"] == "memory"
    assert entry["citations"] == [7]

    assert bio.status()["status"] == "present"
    thread = bio.read()
    assert "# The Autobiography of Unnr" in thread
    assert "## The First Night" in thread
    assert "I began keeping this thread." in thread
    assert "#7" in thread  # witnessed-by line

    assert len(bio.chapters()) == 1
    assert nerve_spy[0]["type"] == "autobiography_chapter"
    assert nerve_spy[0]["data"]["title"] == "The First Night"


def test_record_old_events_are_citable(tmp_state):
    """Chapters may summarize long arcs — any age in the feed is citable."""
    entry = Autobiography().record_chapter("Long Ago", "Five days past.", [103])
    assert entry["citations"] == [103]


def test_myth_mode_is_labeled(tmp_state, nerve_spy):
    bio = Autobiography()
    bio.record_chapter("A Dream", "I flew over the fjord.", [7], mode="myth")
    thread = bio.read()
    assert "(told as myth)" in thread
    assert nerve_spy[0]["data"]["mode"] == "myth"


def test_second_chapter_appends(tmp_state):
    bio = Autobiography()
    bio.record_chapter("One", "first", [101])
    bio.record_chapter("Two", "second", [102])
    assert bio.status()["chapters"] == 2
    thread = bio.read()
    assert thread.count("# The Autobiography of Unnr") == 1  # header written once
    assert "## One" in thread and "## Two" in thread


# --- material -----------------------------------------------------------------

def test_material_includes_mirror_lines(tmp_state):
    (tmp_state / "morning_mirror.jsonl").write_text(json.dumps({
        "ts": "2026-09-25T23:05:00+00:00", "line": "I am Unnr.",
        "citations": [101], "cited": [], "mood": {},
    }) + "\n")
    mat = Autobiography().material()
    assert len(mat["mirror_lines"]) == 1
    assert "I am Unnr" in Autobiography().render_material(mat)


# --- Slice 0 integration -------------------------------------------------------

def test_mirror_sees_thread_present(tmp_state):
    """Once a chapter exists, the Morning Mirror no longer reports thin."""
    import morning_mirror
    bio = Autobiography()
    bio.record_chapter("The First Night", "I began.", [101])
    bundle = morning_mirror.MorningMirror().gather()
    assert bundle["autobiography"]["status"] == "present"
