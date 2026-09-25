"""Tests for muse_aspects.py — Aspects of the Muse."""

import json
import os

import pytest

import muse_aspects
from muse_aspects import GefanRewards, HugrMood, MuseAspects, SkuggiShadow


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    """Isolate state to a temp dir and silence the nerve."""
    monkeypatch.setenv("MUSE_ASPECTS_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(muse_aspects, "_nerve_publish", None)
    return tmp_path


@pytest.fixture
def nerve_spy(tmp_path, monkeypatch):
    """Capture nerve events instead of publishing them."""
    events = []

    def fake_publish(event_type, data, source="muse_aspects"):
        events.append({"type": event_type, "data": data, "source": source})
        return 1

    monkeypatch.setenv("MUSE_ASPECTS_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(muse_aspects, "_nerve_publish", fake_publish)
    return events


# --- HugrMood ---------------------------------------------------------------

def test_mood_starts_near_baseline(tmp_state):
    mood = HugrMood(tmp_state)
    snap = mood.snapshot()["mood"]
    assert snap["valence"] == pytest.approx(0.15, abs=0.05)
    assert snap["energy"] == pytest.approx(0.55, abs=0.05)
    assert snap["tension"] == pytest.approx(0.15, abs=0.05)


def test_mood_nudge_clamps(tmp_state):
    mood = HugrMood(tmp_state)
    mood.nudge(valence=5.0, energy=-5.0, tension=5.0)
    s = mood.snapshot()["mood"]
    assert s["valence"] == 1.0
    assert s["energy"] == 0.0
    assert s["tension"] == 1.0


def test_mood_drift_toward_baseline(tmp_state):
    mood = HugrMood(tmp_state)
    mood.nudge(valence=0.8, energy=0.4, tension=0.6)
    high = mood.snapshot()["mood"]["valence"]
    assert high > 0.8
    # ten hours later the drift should have pulled it back toward baseline
    mood.drift(now=mood.updated_at + 10 * 3600)
    settled = mood.snapshot()["mood"]["valence"]
    assert settled < high
    assert settled == pytest.approx(HugrMood.BASELINE["valence"], abs=0.05)


def test_mood_persists(tmp_state):
    mood = HugrMood(tmp_state)
    mood.nudge(valence=0.3, why="test")
    reloaded = HugrMood(tmp_state)
    assert reloaded.snapshot()["mood"]["valence"] == pytest.approx(
        mood.snapshot()["mood"]["valence"], abs=0.01
    )


def test_mood_shift_emits_nerve_event(nerve_spy, tmp_path):
    mood = HugrMood(tmp_path)
    mood.nudge(valence=0.5, why="big win")
    shifts = [e for e in nerve_spy if e["type"] == "mood_shift"]
    assert len(shifts) == 1
    assert shifts[0]["data"]["why"] == "big win"
    assert "before" in shifts[0]["data"] and "after" in shifts[0]["data"]


def test_small_nudge_stays_silent(nerve_spy, tmp_path):
    mood = HugrMood(tmp_path)
    mood.nudge(valence=0.01, why="tiny")
    assert not [e for e in nerve_spy if e["type"] == "mood_shift"]


# --- GefanRewards ------------------------------------------------------------

def test_reward_record_updates_mood_and_log(nerve_spy, tmp_path):
    aspects = MuseAspects(tmp_path)
    before = aspects.mood.snapshot()["mood"]["valence"]
    entry = aspects.rewards.record("task_completed", "shipped the relay fix")
    after = aspects.mood.snapshot()["mood"]["valence"]
    assert after > before
    assert entry["trigger"] == "task_completed"
    assert entry["domain"] == "craft"
    assert entry["note"] == "shipped the relay fix"
    # JSONL log landed
    logged = [json.loads(l) for l in (tmp_path / "muse_rewards.jsonl").read_text().splitlines()]
    assert logged[-1]["trigger"] == "task_completed"
    # nerve event fired
    rewards = [e for e in nerve_spy if e["type"] == "reward"]
    assert len(rewards) == 1
    assert rewards[0]["data"]["trigger"] == "task_completed"


def test_reward_unknown_trigger_raises(tmp_state):
    rewards = GefanRewards(tmp_state)
    with pytest.raises(ValueError, match="Unknown reward trigger"):
        rewards.record("danced_a_jig")


def test_all_reward_triggers_valid(tmp_state):
    rewards = GefanRewards(tmp_state)
    for trigger in muse_aspects.REWARD_TRIGGERS:
        rewards.record(trigger)
    assert rewards.count() == len(muse_aspects.REWARD_TRIGGERS)


def test_reward_recent_order(tmp_state):
    rewards = GefanRewards(tmp_state)
    rewards.record("tests_green")
    rewards.record("bug_fixed")
    recent = rewards.recent(2)
    assert [r["trigger"] for r in recent] == ["tests_green", "bug_fixed"]


# --- SkuggiShadow ------------------------------------------------------------

def test_shadow_record_raises_tension(nerve_spy, tmp_path):
    aspects = MuseAspects(tmp_path)
    before = aspects.mood.snapshot()["mood"]["tension"]
    entry = aspects.shadow.record("user_correction", "misread the branch strategy")
    after = aspects.mood.snapshot()["mood"]["tension"]
    assert after > before
    assert entry["signal"] == "user_correction"
    assert "growth data" in entry["guidance"]
    logged = [json.loads(l) for l in (tmp_path / "muse_shadow.jsonl").read_text().splitlines()]
    assert logged[-1]["signal"] == "user_correction"
    shadows = [e for e in nerve_spy if e["type"] == "shadow"]
    assert len(shadows) == 1


def test_shadow_unknown_signal_raises(tmp_state):
    shadow = SkuggiShadow(tmp_state)
    with pytest.raises(ValueError, match="Unknown shadow signal"):
        shadow.record("ate_the_moon")


def test_all_shadow_signals_valid(tmp_state):
    shadow = SkuggiShadow(tmp_state)
    for signal in muse_aspects.SHADOW_SIGNALS:
        shadow.record(signal)
    assert shadow.count() == len(muse_aspects.SHADOW_SIGNALS)


# --- Facade ------------------------------------------------------------------

def test_status_shape(tmp_state):
    aspects = MuseAspects(tmp_state)
    aspects.rewards.record("user_delight", "he loved the video")
    aspects.shadow.record("task_failed", "relay test flaked")
    status = aspects.status()
    assert set(status) == {"mood", "rewards_recorded", "shadow_signals",
                           "recent_rewards", "recent_shadow"}
    assert status["rewards_recorded"] == 1
    assert status["shadow_signals"] == 1
    assert status["recent_rewards"] == ["user_delight"]
    assert status["recent_shadow"] == ["task_failed"]


def test_facade_shares_one_mood(tmp_state):
    aspects = MuseAspects(tmp_state)
    assert aspects.rewards.mood is aspects.mood
    assert aspects.shadow.mood is aspects.mood


def test_env_state_dir_override(tmp_path, monkeypatch):
    monkeypatch.setenv("MUSE_ASPECTS_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(muse_aspects, "_nerve_publish", None)
    aspects = MuseAspects()  # no explicit dir -> env wins
    aspects.rewards.record("job_success")
    assert (tmp_path / "muse_rewards.jsonl").exists()


def test_cli_reward_smoke(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MUSE_ASPECTS_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(muse_aspects, "_nerve_publish", None)
    monkeypatch.setattr("sys.argv", ["muse_aspects.py", "reward", "tests_green", "suite is green"])
    muse_aspects.main()
    out = capsys.readouterr().out
    assert "Reward recorded: tests_green" in out
    assert (tmp_path / "muse_rewards.jsonl").exists()
