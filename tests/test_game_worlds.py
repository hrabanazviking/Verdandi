"""Tests for game_worlds — general game-state worlds (Slice 6)."""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import game_worlds as gw
import worlds as _worlds_mod


@pytest.fixture()
def sdir(tmp_path, monkeypatch):
    d = str(tmp_path / "state")
    os.makedirs(d, exist_ok=True)
    monkeypatch.setattr(gw, "_state_dir", lambda: d)
    # keep test game registrations out of the live world registry
    monkeypatch.setattr(_worlds_mod, "_state_dir", lambda: d)
    return d


@pytest.fixture()
def events():
    out = []
    return out


@pytest.fixture()
def emit(events):
    return lambda et, data: events.append((et, data))


def _manual_game(sdir, emit, gid="heimr-game-test"):
    return gw.register_game(gid, "Test Game", "manual",
                           source="test", description="fixture",
                           state_dir=sdir, emit=emit)


def test_register_rejects_bad_prefix(sdir, emit):
    with pytest.raises(ValueError, match="heimr-game-"):
        gw.register_game("heimr-ttrpg-nope", "Nope", "manual",
                         state_dir=sdir, emit=emit)


def test_register_forces_potential_game_kind(sdir, emit):
    rec = _manual_game(sdir, emit)
    assert rec["reality"] == "potential"
    assert rec["world_id"] == "heimr-game-test"
    # the worlds registry agrees: kind game, reality potential
    from worlds import WorldRegistry
    w = WorldRegistry().get("heimr-game-test")
    assert w is not None
    assert w.kind == "game"
    assert w.reality == "potential"


def test_register_rejects_unknown_adapter(sdir, emit):
    with pytest.raises(ValueError, match="adapter"):
        gw.register_game("heimr-game-x", "X", "telepathy",
                         state_dir=sdir, emit=emit)


def test_register_rejects_duplicate(sdir, emit):
    _manual_game(sdir, emit)
    with pytest.raises(ValueError, match="already registered"):
        _manual_game(sdir, emit)


def test_log_refused_for_non_manual_adapter(sdir, emit, tmp_path):
    f = tmp_path / "g.json"
    f.write_text(json.dumps({"score": 1}))
    gw.register_game("heimr-game-file", "File Game", "statefile",
                     source=str(f), state_dir=sdir, emit=emit)
    with pytest.raises(ValueError, match="manual-adapter"):
        gw.log_entry("heimr-game-file", "hand note",
                     state_dir=sdir, emit=emit)


def test_manual_log_sync_emits_labeled_game_state(sdir, emit, events):
    _manual_game(sdir, emit)
    gw.log_entry("heimr-game-test", "first session",
                 state={"score": 10}, provenance="fixture",
                 state_dir=sdir, emit=emit)
    kinds = [et for et, _ in events]
    assert "game_log_entry" in kinds
    assert "game_state" in kinds
    _, data = next(p for p in events if p[0] == "game_state")
    assert data["world_id"] == "heimr-game-test"
    assert data["reality"] == "potential"
    assert data["state"]["score"] == 10
    snap = gw.get_snapshot("heimr-game-test", state_dir=sdir)
    assert snap["reality"] == "potential"


def test_sync_dedup_no_event_without_change(sdir, emit, events):
    _manual_game(sdir, emit)
    gw.log_entry("heimr-game-test", "s1", state={"score": 10},
                 state_dir=sdir, emit=emit)
    n = len(events)
    rep = gw.sync("heimr-game-test", state_dir=sdir, emit=emit)
    assert rep["changed"] is False
    assert len(events) == n  # silent when nothing changed


def test_sync_detects_changed_keys(sdir, emit, events):
    _manual_game(sdir, emit)
    gw.log_entry("heimr-game-test", "s1", state={"score": 10, "level": 1},
                 state_dir=sdir, emit=emit)
    gw.log_entry("heimr-game-test", "s2", state={"score": 12, "level": 1},
                 state_dir=sdir, emit=emit)
    _, data = [p for p in events if p[0] == "game_state"][-1]
    assert data["changed_keys"] == ["score"]


def test_statefile_adapter_json_key_path(sdir, emit, tmp_path):
    f = tmp_path / "save.json"
    f.write_text(json.dumps({"game": {"turn": 7, "hp": 33}}))
    gw.register_game("heimr-game-file", "File Game", "statefile",
                     source=str(f),
                     adapter_config={"key_path": "game"},
                     state_dir=sdir, emit=emit)
    rep = gw.sync("heimr-game-file", state_dir=sdir, emit=emit)
    assert rep["changed"] is True
    snap = gw.get_snapshot("heimr-game-file", state_dir=sdir)
    assert snap["state"] == {"turn": 7, "hp": 33}
    assert snap["reality"] == "potential"


def test_statefile_adapter_missing_file_reports_error(sdir, emit):
    gw.register_game("heimr-game-ghost", "Ghost", "statefile",
                     source="/nonexistent/save.json",
                     state_dir=sdir, emit=emit)
    rep = gw.sync("heimr-game-ghost", state_dir=sdir, emit=emit)
    assert rep["changed"] is True  # first snapshot still recorded
    snap = gw.get_snapshot("heimr-game-ghost", state_dir=sdir)
    assert "_error" in snap["state"]


def test_api_adapter(monkeypatch, sdir, emit):
    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"data": {"players": 3}}'

    monkeypatch.setattr(gw.urllib.request, "urlopen",
                        lambda req, timeout=20: FakeResp())
    gw.register_game("heimr-game-api", "API Game", "api",
                     source="https://example.invalid/state",
                     adapter_config={"key_path": "data"},
                     state_dir=sdir, emit=emit)
    rep = gw.sync("heimr-game-api", state_dir=sdir, emit=emit)
    assert rep["changed"] is True
    snap = gw.get_snapshot("heimr-game-api", state_dir=sdir)
    assert snap["state"] == {"players": 3}


def test_api_adapter_unreachable(monkeypatch, sdir, emit):
    def boom(req, timeout=20):
        raise OSError("no route")
    monkeypatch.setattr(gw.urllib.request, "urlopen", boom)
    gw.register_game("heimr-game-down", "Down Game", "api",
                     source="https://example.invalid/x",
                     state_dir=sdir, emit=emit)
    rep = gw.sync("heimr-game-down", state_dir=sdir, emit=emit)
    assert rep["changed"] is True
    snap = gw.get_snapshot("heimr-game-down", state_dir=sdir)
    assert "_error" in snap["state"]


def test_log_unknown_game(sdir, emit):
    with pytest.raises(ValueError, match="unknown game"):
        gw.log_entry("heimr-game-nope", "x", state_dir=sdir, emit=emit)


def test_sync_unknown_game(sdir, emit):
    with pytest.raises(ValueError, match="unknown game"):
        gw.sync("heimr-game-nope", state_dir=sdir, emit=emit)


def test_sync_all_continues_past_failure(sdir, emit, monkeypatch):
    _manual_game(sdir, emit)
    gw.register_game("heimr-game-bad", "Bad", "api", source="",
                     state_dir=sdir, emit=emit)
    real_sync = gw.sync

    def flaky(gid, state_dir=None, emit=None):
        if gid == "heimr-game-bad":
            raise RuntimeError("boom")
        return real_sync(gid, state_dir=state_dir, emit=emit)

    monkeypatch.setattr(gw, "sync", flaky)
    reps = gw.sync_all(state_dir=sdir, emit=emit)
    by_id = {r["game_id"]: r for r in reps}
    assert "error" in by_id["heimr-game-bad"]
    assert by_id["heimr-game-test"]["changed"] in (True, False)


def test_firewall_entries_always_potential(sdir, emit):
    _manual_game(sdir, emit)
    entry = gw.log_entry("heimr-game-test", "s1",
                         state={"reality": "manifest", "score": 1},
                         state_dir=sdir, emit=emit)
    assert entry["reality"] == "potential"  # label wins, not the payload
    assert entry["state"]["reality"] == "manifest"  # payload untouched...
    snap = gw.get_snapshot("heimr-game-test", state_dir=sdir)
    assert snap["reality"] == "potential"  # ...but the snapshot label holds
