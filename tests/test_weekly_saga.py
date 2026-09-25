"""Behavior-contract tests for weekly_saga.py — Slice 1 of "The Becoming".

Design laws under test:
  - Real signals only: patterns cite >= 3 real, in-window sequenced events.
  - No invented citations, no out-of-window citations.
  - "No pattern found this week" is a valid saga.
  - The saga persists (jsonl + readable book) and announces itself on the nerve.
"""

import json
import os

import pytest

import weekly_saga
from weekly_saga import WeeklySaga

NOW = 1_789_000_000.0  # fixed "now" for deterministic windows (2026-09-25)
DAY = 24 * 3600


def _iso(ts):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


@pytest.fixture()
def saga_dir(tmp_path, monkeypatch):
    """Isolated state dir with a fake week of nerve history; nerve silenced."""
    d = tmp_path / "state"
    d.mkdir()

    # Sequenced feed events: seqs 1-4 inside the window, seq 5 older than 7 days.
    feed = [
        {"_seq": 1, "_ts": _iso(NOW - 6 * DAY), "type": "reward",
         "data": {"trigger": "repo_shipped"}, "source": "muse"},
        {"_seq": 2, "_ts": _iso(NOW - 5 * DAY), "type": "reward",
         "data": {"trigger": "task_completed"}, "source": "muse"},
        {"_seq": 3, "_ts": _iso(NOW - 4 * DAY), "type": "shadow",
         "data": {"signal": "test_failure"}, "source": "muse"},
        {"_seq": 4, "_ts": _iso(NOW - 1 * DAY), "type": "reward",
         "data": {"trigger": "repo_shipped"}, "source": "muse"},
        {"_seq": 5, "_ts": _iso(NOW - 10 * DAY), "type": "reward",
         "data": {"trigger": "old_news"}, "source": "muse"},
        {"_seq": 6, "_ts": _iso(NOW - 11 * DAY), "type": "reward",
         "data": {"trigger": "older_news"}, "source": "muse"},
        {"_seq": 7, "_ts": _iso(NOW - 12 * DAY), "type": "shadow",
         "data": {"signal": "old_stumble"}, "source": "muse"},
        # fallback line: no _seq, must never be citable
        {"_ts": _iso(NOW - 1 * DAY), "type": "reward",
         "data": {"trigger": "ghost"}, "source": "muse", "_fallback": True},
    ]
    _write_jsonl(d / "nerve_feed.jsonl", feed)
    _write_jsonl(d / "muse_rewards.jsonl", [
        {"ts": _iso(NOW - 1 * DAY), "trigger": "repo_shipped", "note": "fresh"},
        {"ts": _iso(NOW - 20 * DAY), "trigger": "ancient", "note": "too old"},
    ])
    _write_jsonl(d / "muse_shadow.jsonl", [
        {"ts": _iso(NOW - 2 * DAY), "signal": "test_failure", "note": "a bad run"},
    ])
    _write_jsonl(d / "morning_mirror.jsonl", [
        {"ts": _iso(NOW - 1 * DAY), "line": "a mirror line"},
    ])

    monkeypatch.setattr(weekly_saga, "_nerve_publish", None)
    return str(d)


@pytest.fixture()
def ws(saga_dir):
    return WeeklySaga(state_dir=saga_dir)


# ---------------------------------------------------------------------------
# evidence gathering
# ---------------------------------------------------------------------------

def test_gather_window_is_seven_days(ws):
    b = ws.gather(now=NOW)
    assert b["window_end"] - b["window_start"] == pytest.approx(7 * 24 * 3600)


def test_gather_filters_everything_to_window(ws):
    b = ws.gather(now=NOW)
    assert [r["trigger"] for r in b["rewards"]] == ["repo_shipped"]
    assert [s["signal"] for s in b["shadows"]] == ["test_failure"]
    assert [e["seq"] for e in b["events"]] == [1, 2, 3, 4]
    assert len(b["mirrors"]) == 1


def test_gather_empty_state_is_honest(tmp_path):
    empty = WeeklySaga(state_dir=str(tmp_path / "empty"))
    b = empty.gather(now=NOW)
    assert b["rewards"] == [] and b["shadows"] == [] and b["events"] == []


# ---------------------------------------------------------------------------
# recording: validation
# ---------------------------------------------------------------------------

def test_record_rejects_empty_title_or_text(ws):
    with pytest.raises(ValueError):
        ws.record_saga("", "some text", now=NOW)
    with pytest.raises(ValueError):
        ws.record_saga("title", "   ", now=NOW)


def test_record_rejects_pattern_with_fewer_than_three_citations(ws):
    with pytest.raises(ValueError, match="at least 3"):
        ws.record_saga("t", "text",
                       [{"name": "thin", "claim": "a claim", "citations": [1, 2]}],
                       now=NOW)


def test_record_rejects_unknown_sequence(ws):
    with pytest.raises(ValueError, match="does not exist"):
        ws.record_saga("t", "text",
                       [{"name": "fake", "claim": "a claim", "citations": [1, 2, 999]}],
                       now=NOW)


def test_record_rejects_out_of_window_citation(ws):
    # seq 5 is real but 10 days old: outside this saga's week
    with pytest.raises(ValueError, match="outside this saga"):
        ws.record_saga("t", "text",
                       [{"name": "stale", "claim": "a claim", "citations": [1, 2, 5]}],
                       now=NOW)


def test_record_rejects_pattern_missing_name_or_claim(ws):
    with pytest.raises(ValueError):
        ws.record_saga("t", "text",
                       [{"claim": "no name", "citations": [1, 2, 3]}], now=NOW)
    with pytest.raises(ValueError):
        ws.record_saga("t", "text",
                       [{"name": "no claim", "citations": [1, 2, 3]}], now=NOW)


def test_record_with_no_patterns_is_valid(ws):
    rec = ws.record_saga("a quiet week", "Nothing much stirred.", now=NOW)
    assert rec["patterns"] == []
    assert "No pattern found" in open(ws.book_path, encoding="utf-8").read()


# ---------------------------------------------------------------------------
# recording: persistence and announcement
# ---------------------------------------------------------------------------

def test_record_persists_jsonl_book_and_nerve(ws, saga_dir, monkeypatch):
    emitted = []
    monkeypatch.setattr(weekly_saga, "_nerve_publish",
                        lambda et, data, src: emitted.append((et, data, src)))

    rec = ws.record_saga(
        "the building week", "I built things.",
        [{"name": "shipper", "claim": "shipping energizes me",
          "citations": ["3", 1, 2, 2, 4]}],  # strings ok, dupes collapse
        now=NOW)

    assert rec["patterns"][0]["citations"] == [1, 2, 3, 4]

    rows = [json.loads(l) for l in open(os.path.join(saga_dir, "weekly_saga.jsonl"))]
    assert rows[-1]["title"] == "the building week"

    book = open(ws.book_path, encoding="utf-8").read()
    assert "the building week" in book and "shipper" in book

    assert emitted and emitted[0][0] == "weekly_saga"
    assert emitted[0][2] == "weekly_saga"


def test_sagas_and_last_read_back(ws):
    ws.record_saga("one", "text one", now=NOW)
    ws.record_saga("two", "text two", now=NOW)
    assert [s["title"] for s in ws.sagas()] == ["one", "two"]
    assert ws.last()["title"] == "two"


def test_week_offset_shifts_window(ws):
    # seqs 5-7 (10-12 days old) belong to week_offset=1, not week 0
    rec = ws.record_saga("last week", "older text",
                         [{"name": "old", "claim": "an old pattern",
                           "citations": [5, 6, 7]}],
                         week_offset=1, now=NOW)
    assert rec["patterns"][0]["citations"] == [5, 6, 7]

    b = ws.gather(week_offset=1, now=NOW)
    assert [e["seq"] for e in b["events"]] == [7, 6, 5]


def test_render_includes_counts_and_seq_range(ws):
    text = ws.render(ws.gather(now=NOW))
    assert "Rewards (1)" in text
    assert "Shadows (1)" in text
    assert "#1 → #4" in text
