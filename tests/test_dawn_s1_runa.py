"""Dawn forge 2026-10-11: slices 1, 2 (+12 runa CLI part).

runa_mood_arousal_system.py:
  S1: integrate_reward_system / integrate_negative_system read the stat
      keys the writers actually emit (stats.total_rewards /
      stats.total_negatives / stats.total_intensity).
  S2: load_state survives non-dict / wrong-shaped JSON (isinstance +
      OSError guards); save_state is atomic; corrupt state is LOUD.
  S12: CLI `event`/`stimulate` with non-numeric args -> exit 2, one-line
      stderr, no traceback.
"""
import json
import sys

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "heartbeat"))

import runa_mood_arousal_system as rmas


@pytest.fixture()
def iso(tmp_path, monkeypatch):
    sd = tmp_path / "state"
    sd.mkdir()
    monkeypatch.setattr(rmas, "STATE_DIR", sd)
    monkeypatch.setattr(rmas, "MOOD_STATE_FILE", sd / "runa_mood_arousal.json")
    return sd


def _fresh(iso):
    s = rmas.RunaMoodArousalSystem()
    s.mood.valence = 0.3
    s.mood.energy = 0.2
    s.mood.tension = -0.1
    s.mood.clamp()
    return s


# --- S1 -----------------------------------------------------------------
def test_integrate_reward_reads_real_writer_keys(iso):
    (iso / "runa_rewards.json").write_text(json.dumps(
        {"stats": {"total_rewards": 5, "total_intensity": 25.0}}))
    s = _fresh(iso)
    s.integrate_reward_system()
    # avg = 25/5 = 5 -> valence += 5*0.003 = 0.015
    assert s.mood.valence == pytest.approx(0.315)
    assert s.mood.energy == pytest.approx(0.21)
    assert s.mood.tension == pytest.approx(-0.105)


def test_integrate_negative_reads_real_writer_keys(iso):
    (iso / "runa_negative.json").write_text(json.dumps(
        {"stats": {"total_negatives": 3, "total_intensity": 12.0}}))
    s = _fresh(iso)
    s.integrate_negative_system()
    # avg = 12/3 = 4 -> valence -= 4*0.003 = 0.012
    assert s.mood.valence == pytest.approx(0.288)
    assert s.mood.energy == pytest.approx(0.196)
    assert s.mood.tension == pytest.approx(-0.092)


def test_integrate_missing_files_is_noop(iso):
    s = _fresh(iso)
    s.integrate_reward_system()
    s.integrate_negative_system()
    assert s.mood.valence == pytest.approx(0.3)


# --- S2 -----------------------------------------------------------------
@pytest.mark.parametrize("bad", ["[1,2]", '"just a string"', "42", "null"])
def test_load_state_survives_wrong_shape_json(iso, bad):
    (iso / "runa_mood_arousal.json").write_text(bad)
    s = rmas.RunaMoodArousalSystem()  # must not raise
    assert s.mood.valence == pytest.approx(s.baseline_valence)
    assert s.arousal.orgasm_count == 0


def test_corrupt_state_is_loud_not_silent(iso, caplog):
    s = _fresh(iso)
    s.save_state()
    path = iso / "runa_mood_arousal.json"
    raw = path.read_text()
    path.write_text(raw[: len(raw) // 3])  # torn write
    with caplog.at_level("WARNING"):
        s2 = rmas.RunaMoodArousalSystem()
    assert any("corrupt" in r.getMessage().lower() or "invalid" in r.getMessage().lower()
               for r in caplog.records), "corrupt state must be logged loudly"
    assert s2.mood.valence == pytest.approx(s2.baseline_valence)


def test_save_load_roundtrip(iso):
    s = _fresh(iso)
    s.mood.valence = 0.9
    s.arousal.orgasm_count = 7
    s.save_state()
    s2 = rmas.RunaMoodArousalSystem()
    assert s2.mood.valence == pytest.approx(0.9)
    assert s2.arousal.orgasm_count == 7


def test_save_state_leaves_no_tmp_lingering(iso):
    s = _fresh(iso)
    s.save_state()
    leftovers = [p for p in iso.iterdir() if p.suffix == ".tmp" or p.name.endswith(".tmp")]
    assert leftovers == []
    assert json.loads((iso / "runa_mood_arousal.json").read_text())["valence"] == pytest.approx(0.3)


# --- S12 (runa_mood CLI part) --------------------------------------------
def test_cli_event_bad_intensity_exits_2_no_traceback(iso, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["runa_mood_arousal_system.py", "event", "volmarr_praise", "abc"])
    with pytest.raises(SystemExit) as exc:
        rmas.main()
    assert exc.value.code == 2
    out, err = capsys.readouterr()
    assert "Traceback" not in out and "Traceback" not in err
    assert err.strip() != ""


def test_cli_stimulate_bad_duration_exits_2_no_traceback(iso, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["runa_mood_arousal_system.py", "stimulate", "touch", "xyz"])
    with pytest.raises(SystemExit) as exc:
        rmas.main()
    assert exc.value.code == 2
    out, err = capsys.readouterr()
    assert "Traceback" not in out and "Traceback" not in err


def test_cli_event_valid_still_works(iso, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["runa_mood_arousal_system.py", "event", "volmarr_praise", "1.5"])
    rmas.main()  # must not raise
    out, _ = capsys.readouterr()
    assert "Event applied" in out
