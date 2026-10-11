"""Dawn forge 2026-10-11: slices 9, 10, 11.

S9:  push_reward.record_push with an unknown tier raises ValueError (naming
     the valid tiers), never a bare KeyError.
S10: runa reward/negative DBs survive corruption (fire_*/get_stats fall back
     to empty history LOUDLY and rewrite a valid DB); history lists are
     bounded (<= 500 entries).
S11: the runa/push nerve-emit path resolves nervous_system from the repo
     directory, not ~/.hermes/state (where it can never exist).
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "heartbeat"))

import push_reward
import runa_reward_system as rrs
import runa_negative_system as rns


@pytest.fixture()
def iso(tmp_path, monkeypatch):
    sd = tmp_path / "state"
    sd.mkdir()
    monkeypatch.setattr(push_reward, "STATE_FILE", sd / "push_history.json")
    monkeypatch.setattr(rrs, "REWARD_DB", sd / "runa_rewards.json")
    monkeypatch.setattr(rns, "NEGATIVE_DB", sd / "runa_negative.json")
    return sd


# --- S9 -------------------------------------------------------------------
def test_record_push_unknown_tier_raises_valueerror(iso):
    with pytest.raises(ValueError) as exc:
        push_reward.record_push("verdandi", 1, "bogus_tier")
    assert "bogus_tier" in str(exc.value)
    for tier in ("trivial", "minor", "moderate", "major", "critical"):
        assert tier in str(exc.value)


def test_record_push_valid_tiers_still_record(iso):
    for tier in ("trivial", "minor", "moderate", "major", "critical"):
        push_reward.record_push("verdandi", 1, tier)
    hist = push_reward.load_push_history()
    assert hist["total_pushes"] == 5


# --- S10 ------------------------------------------------------------------
def test_fire_reward_survives_corrupt_db(iso, caplog):
    (iso / "runa_rewards.json").write_text("{corrupt!!")
    with caplog.at_level("WARNING"):
        out = rrs.fire_reward("task_for_volmarr", context="test")
    assert out is not None  # the reward still fires
    data = json.loads((iso / "runa_rewards.json").read_text())
    assert isinstance(data, dict) and len(data["rewards"]) == 1
    assert any("corrupt" in r.getMessage().lower() for r in caplog.records)


def test_fire_negative_survives_corrupt_db(iso, caplog):
    (iso / "runa_negative.json").write_text("[not json")
    with caplog.at_level("WARNING"):
        out = rns.fire_negative("volmarr_disappointed", context="test")
    assert out is not None
    data = json.loads((iso / "runa_negative.json").read_text())
    assert isinstance(data, dict) and len(data["negatives"]) == 1


def test_get_stats_survives_corrupt_db(iso):
    (iso / "runa_rewards.json").write_text("{corrupt!!")
    (iso / "runa_negative.json").write_text("{corrupt!!")
    assert rrs.get_stats()["total_rewards"] == 0
    assert rns.get_stats()["total_negatives"] == 0


def test_reward_history_is_bounded(iso):
    for _ in range(600):
        rrs.fire_reward("task_for_volmarr", context="x")
    data = json.loads((iso / "runa_rewards.json").read_text())
    assert len(data["rewards"]) <= 500
    assert data["stats"]["total_rewards"] == 600  # stats stay cumulative


def test_negative_history_is_bounded(iso):
    for _ in range(600):
        rns.fire_negative("volmarr_disappointed", context="x")
    data = json.loads((iso / "runa_negative.json").read_text())
    assert len(data["negatives"]) <= 500
    assert data["stats"]["total_negatives"] == 600


# --- S11 ------------------------------------------------------------------
def test_nerve_emit_helper_resolves_repo_root():
    """The emit path must insert the repo root (where nervous_system.py
    lives), never ~/.hermes/state."""
    for mod in (rrs, rns, push_reward):
        publish = mod._nerve_publish()
        assert publish.__module__ == "nervous_system"
        assert Path(sys.modules["nervous_system"].__file__).parent == REPO


def test_reward_event_reaches_nerve(iso, monkeypatch):
    calls = []

    class FakeNS:
        __file__ = str(REPO / "nervous_system.py")

        @staticmethod
        def publish_event_sync(event_type, data=None, source=None):
            calls.append((event_type, data, source))
            return {"nerve_type": "sent"}

    monkeypatch.setitem(sys.modules, "nervous_system", FakeNS)
    rrs.fire_reward("task_for_volmarr", context="nerve-probe")
    assert calls, "fire_reward never called publish_event_sync"
    event_type, data, source = calls[0]
    assert event_type == "runa_reward"
    assert data["trigger"] == "task_for_volmarr"
    assert source == "reward_system"


def test_negative_event_reaches_nerve(iso, monkeypatch):
    calls = []

    class FakeNS:
        __file__ = str(REPO / "nervous_system.py")

        @staticmethod
        def publish_event_sync(event_type, data=None, source=None):
            calls.append((event_type, data, source))
            return {"nerve_type": "sent"}

    monkeypatch.setitem(sys.modules, "nervous_system", FakeNS)
    rns.fire_negative("volmarr_disappointed", context="nerve-probe")
    assert calls, "fire_negative never called publish_event_sync"
    assert calls[0][0] == "runa_negative"
    assert calls[0][2] == "negative_system"
