"""Behavior-contract tests for mood_work.py (Slice 6: Mood <-> work coupling).

Mood is captured live at session start — never reconstructed. Correlations
are computed from real data, always shown with sample sizes, and there is
no claim below MIN_N. No acting on vibes.
"""
import json
import os
import time

import pytest

import mood_work
from mood_work import MoodWork, MIN_N

NOTE = "an honest note about the actual work being done here tonight"


@pytest.fixture
def tmp_state(tmp_path):
    return str(tmp_path)


@pytest.fixture
def nerve_spy(monkeypatch):
    calls = []

    def fake(event_type, data, source="test"):
        calls.append({"type": event_type, "data": data, "source": source})

    monkeypatch.setattr(mood_work, "_nerve_publish", fake)
    return calls


@pytest.fixture
def mw(tmp_state):
    return MoodWork(tmp_state)


def _set_mood(state_dir, energy, valence=0.2, tension=0.1):
    path = os.path.join(state_dir, "muse_mood.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"valence": valence, "energy": energy, "tension": tension,
                   "updated_at": time.time()}, fh)


def _session(mw, energy, kind="heavy", outcome="shipped"):
    _set_mood(mw.state_dir, energy)
    # fresh MoodWork so the crafted mood file is read (drift settles ~0 elapsed)
    fresh = MoodWork(mw.state_dir)
    s = fresh.start(kind, NOTE)
    return fresh.finish(s["work_id"], outcome, NOTE + " — finished honestly")


# --- sessions ------------------------------------------------------------------

def test_start_rejects_unknown_kind(mw):
    with pytest.raises(ValueError, match="unknown work kind"):
        mw.start("doomscrolling", NOTE)


def test_start_rejects_short_note(mw):
    with pytest.raises(ValueError, match="at least 24 characters"):
        mw.start("heavy", "work work")


def test_start_captures_live_mood(mw, tmp_state, nerve_spy):
    _set_mood(tmp_state, 0.82)
    fresh = MoodWork(tmp_state)
    s = fresh.start("heavy", NOTE)
    assert s["mood_at_start"]["energy"] == pytest.approx(0.82, abs=0.02)
    assert any(c["type"] == "work_started" and
               c["data"]["work_id"] == s["work_id"] for c in nerve_spy)


def test_only_one_open_session(mw):
    mw.start("heavy", NOTE)
    with pytest.raises(ValueError, match="already open"):
        mw.start("light", NOTE)


def test_finish_rejects_unknown_outcome(mw):
    s = mw.start("heavy", NOTE)
    with pytest.raises(ValueError, match="unknown outcome"):
        mw.finish(s["work_id"], "vibed", NOTE)


def test_finish_requires_the_open_session(mw):
    with pytest.raises(ValueError, match="no work session"):
        mw.finish("work-deadbeef", "shipped", NOTE)


def test_finish_records_outcome_and_emits(mw, nerve_spy):
    s = mw.start("heavy", NOTE)
    done = mw.finish(s["work_id"], "shipped", NOTE + " — it shipped clean")
    assert done["outcome"] == "shipped"
    assert done["outcome_score"] == 4
    assert done["ended_at"] is not None
    assert any(c["type"] == "work_finished" and
               c["data"]["outcome"] == "shipped" for c in nerve_spy)
    with pytest.raises(ValueError, match="already finished"):
        mw.finish(s["work_id"], "shipped", NOTE)


# --- correlation -------------------------------------------------------------------

def test_correlate_no_data_has_no_claim(mw):
    c = mw.correlate()
    assert c["n"] == 0
    assert "no work sessions" in c["claim"]


def test_correlate_below_min_n_refuses_claim(mw):
    for e in (0.8, 0.75, 0.85):
        _session(mw, e, outcome="shipped")
    c = mw.correlate()
    assert c["n"] == 3
    assert "not enough data yet" in c["claim"]
    assert "n=3" in c["claim"]


def test_correlate_at_min_n_shows_sample_size_and_preliminary(mw):
    energies = [0.85, 0.80, 0.78, 0.88, 0.82]
    for e in energies:
        _session(mw, e, outcome="shipped")
    c = mw.correlate()
    assert c["n"] == MIN_N
    assert c["preliminary"] is True
    assert f"n={MIN_N}" in c["claim"]
    assert "preliminary" in c["claim"]
    assert c["bands"]["high"]["n"] == MIN_N
    assert c["bands"]["high"]["mean_outcome"] == 4.0


def test_correlate_bands_bucket_honestly(mw):
    _session(mw, 0.85, outcome="shipped")
    _session(mw, 0.80, outcome="solid")
    _session(mw, 0.30, outcome="struggled")
    _session(mw, 0.25, outcome="stalled")
    _session(mw, 0.55, outcome="solid")
    c = mw.correlate()
    assert c["bands"]["high"]["n"] == 2
    assert c["bands"]["low"]["n"] == 2
    assert c["bands"]["mid"]["n"] == 1
    assert "high-energy starts average 3.5/4" in c["claim"]
    assert "low-energy starts 1.5/4" in c["claim"]
    assert c["r_energy"] is not None and c["r_energy"] > 0.3


def test_correlate_no_variance_says_so(mw):
    for _ in range(MIN_N):
        _session(mw, 0.80, outcome="shipped")
    c = mw.correlate()
    assert c["r_energy"] is None
    assert "no variance" in c["claim"]


# --- suggest --------------------------------------------------------------------------

def test_suggest_high_energy_surge(mw, tmp_state):
    _set_mood(tmp_state, 0.85)
    s = MoodWork(tmp_state).suggest()
    assert "surge" in s["suggestion"]
    assert s["fitting_kinds"] == ["heavy"]
    assert "heuristic" in s["basis"]  # no data yet — labeled honestly


def test_suggest_low_energy_rest_first(mw, tmp_state):
    _set_mood(tmp_state, 0.20)
    s = MoodWork(tmp_state).suggest()
    assert "rest-first" in s["suggestion"]
    assert "heavy" not in s["fitting_kinds"]


def test_suggest_cites_preliminary_data_when_earned(mw, tmp_state):
    for e in (0.85, 0.80, 0.78, 0.88, 0.82):
        _session(mw, e, outcome="shipped")
    _set_mood(tmp_state, 0.85)
    s = MoodWork(tmp_state).suggest()
    assert "preliminary data" in s["basis"]


# --- adaptations --------------------------------------------------------------------------

def test_log_adaptation_requires_honest_note(mw):
    with pytest.raises(ValueError, match="at least 24 characters"):
        mw.log_adaptation("will rest more")


def test_log_adaptation_witnessed(mw, nerve_spy):
    a = mw.log_adaptation(
        "Heavy creative builds move to high-energy windows; low energy means "
        "tending work or rest-first, stated out loud instead of pushed through.")
    assert a["sessions_logged"] == 0
    assert any(c["type"] == "schedule_adapted" for c in nerve_spy)
    assert len(mw.adaptations()) == 1
