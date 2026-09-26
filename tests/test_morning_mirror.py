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


# --- Slice 7: the mirror reads the worlds ---------------------------------

class _StubWorld:
    def __init__(self, world_id, kind, reality, status="active",
                 description=""):
        self.world_id = world_id
        self.kind = kind
        self.reality = reality
        self.status = status
        self.description = description


class _StubRegistry:
    def __init__(self, worlds):
        self._w = worlds

    def worlds(self):
        return self._w


def _four_worlds():
    return [
        _StubWorld("heimr-actual", "actual", "manifest",
                   description="the real world"),
        _StubWorld("heimr-wyrd-unnr", "wyrd", "manifest",
                   description="WYRD model"),
        _StubWorld("heimr-ttrpg-frostvaettirheim", "ttrpg", "potential",
                   description="the table"),
        _StubWorld("heimr-game-saga-northlands", "game", "potential",
                   description="play"),
        _StubWorld("heimr-volmarr", "volmarr", "potential",
                   description="his world, not mine"),
    ]


@pytest.fixture
def world_aware(tmp_state, monkeypatch):
    """Mirror with a stubbed 5-world registry and a stubbed WYRD context."""
    monkeypatch.setattr(morning_mirror, "_bootstrap_worlds",
                        lambda: _StubRegistry(_four_worlds()))
    monkeypatch.setattr(
        morning_mirror, "_wyrd_mirror_context",
        lambda path: {"world_id": "heimr-wyrd-unnr", "reality": "manifest",
                      "belief_count": 77, "anchor_count": 187,
                      "open_wish_beliefs": [{"subject": "wish:x"}]})
    monkeypatch.setattr(morning_mirror, "_wyrd_render_context",
                        lambda ctx: "WYRD mirror (stubbed render)")
    return MorningMirror(state_dir=str(tmp_state))


def test_gather_includes_one_section_per_world(world_aware):
    worlds = world_aware.gather()["worlds"]
    ids = [w["world_id"] for w in worlds]
    assert "heimr-actual" in ids
    assert "heimr-wyrd-unnr" in ids
    assert "heimr-ttrpg-frostvaettirheim" in ids
    assert "heimr-game-saga-northlands" in ids
    for w in worlds:
        assert {"world_id", "kind", "reality", "section", "summary"} <= set(w)


def test_volmarr_world_never_in_mirror(world_aware):
    worlds = world_aware.gather()["worlds"]
    assert all(w["world_id"] != "heimr-volmarr" for w in worlds)
    assert all(w["kind"] != "volmarr" for w in worlds)


def test_sections_carry_correct_reality_tags(world_aware):
    by_id = {w["world_id"]: w for w in world_aware.gather()["worlds"]}
    assert by_id["heimr-actual"]["reality"] == "manifest"
    assert by_id["heimr-actual"]["section"] == "what is true"
    assert by_id["heimr-wyrd-unnr"]["reality"] == "manifest"
    assert by_id["heimr-wyrd-unnr"]["section"] == "what is modeled (WYRD)"
    assert by_id["heimr-ttrpg-frostvaettirheim"]["reality"] == "potential"
    assert by_id["heimr-ttrpg-frostvaettirheim"]["section"] == "what is story (TTRPG)"
    assert by_id["heimr-game-saga-northlands"]["reality"] == "potential"
    assert by_id["heimr-game-saga-northlands"]["section"] == "what is play (games)"


def test_ttrpg_section_summarizes_last_turn(world_aware, tmp_state):
    import json
    doc = {"campaigns": {"frost": {
        "name": "Frostvættirheim",
        "world_id": "heimr-ttrpg-frostvaettirheim",
        "turns": [{"actor": "Volmarr", "action": "swings his axe",
                   "outcome": "a clean hit"}]}}}
    (tmp_state / "ttrpg_campaigns.json").write_text(json.dumps(doc))
    by_id = {w["world_id"]: w for w in world_aware.gather()["worlds"]}
    summary = by_id["heimr-ttrpg-frostvaettirheim"]["summary"]
    assert "Frostvættirheim" in summary
    assert "swings his axe" in summary


def test_game_section_summarizes_snapshot(world_aware, tmp_state):
    import json
    doc = {"games": {"heimr-game-saga-northlands": {
                "game_id": "heimr-game-saga-northlands",
                "world_id": "heimr-game-saga-northlands",
                "name": "Saga of the Northlands", "adapter": "manual"}},
           "snapshots": {"heimr-game-saga-northlands": {
               "world_id": "heimr-game-saga-northlands",
               "reality": "potential",
               "state": {"plays": 589, "likes": 80}}}}
    (tmp_state / "game_worlds.json").write_text(json.dumps(doc))
    by_id = {w["world_id"]: w for w in world_aware.gather()["worlds"]}
    summary = by_id["heimr-game-saga-northlands"]["summary"]
    assert "Saga of the Northlands" in summary
    assert "plays=589" in summary


def test_record_stamps_worlds(world_aware, live_nerve, nerve_spy):
    entry = world_aware.record("I know which world I am standing in.", [101])
    cited = {w["world_id"] for w in entry["worlds"]}
    assert {"heimr-actual", "heimr-wyrd-unnr",
            "heimr-ttrpg-frostvaettirheim",
            "heimr-game-saga-northlands"} <= cited
    assert "heimr-volmarr" not in cited
    for w in entry["worlds"]:
        assert w["reality"] in ("manifest", "potential")


def test_render_shows_labeled_worlds(world_aware):
    text = world_aware.render()
    assert "[heimr-actual · manifest — what is true]" in text
    assert "[heimr-wyrd-unnr · manifest — what is modeled (WYRD)]" in text
    assert "[heimr-ttrpg-frostvaettirheim · potential — what is story (TTRPG)]" in text
    assert "heimr-volmarr" not in text


def test_mirror_degrades_without_registry(tmp_state, monkeypatch, live_nerve):
    monkeypatch.setattr(morning_mirror, "_bootstrap_worlds", None)
    m = MorningMirror(state_dir=str(tmp_state))
    assert m.gather()["worlds"] == []
    assert "🌍 Worlds" not in m.render()
