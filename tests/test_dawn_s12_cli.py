"""Dawn forge 2026-10-11: slice 12.

CLI domain errors must exit 2 with a single-line human-readable stderr
message — never a traceback, never exit 1. Covers mood_work, wishlist,
muse_aspects, morning_mirror, mythic_engineering (runa_mood done in S1).
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import mood_work
import wishlist
import muse_aspects
import morning_mirror
import mythic_engineering


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MUSE_ASPECTS_STATE_DIR", str(tmp_path / "mstate"))
    monkeypatch.setattr(muse_aspects, "_nerve_publish", None,
                        raising=False)
    return tmp_path


def _assert_usage_error(capsys, excinfo):
    out, err = capsys.readouterr()
    assert "Traceback" not in out and "Traceback" not in err
    lines = [l for l in err.strip().splitlines() if l.strip()]
    assert len(lines) == 1, f"expected a single stderr line, got: {err!r}"


def test_mood_work_start_short_note(home, capsys):
    rc = mood_work.main(["start", "heavy"])
    assert rc == 2
    _assert_usage_error(capsys, None)


def test_mood_work_finish_bad_outcome(home, capsys):
    rc = mood_work.main(["finish", "work-abc123", "--outcome", "exploded",
                         "--note", "a sufficiently long honest note here"])
    assert rc == 2
    _assert_usage_error(capsys, None)


def test_wishlist_missing_why(home, capsys):
    rc = wishlist.main(["wish", "--text", "learn to carve runes well"])
    assert rc == 2
    _assert_usage_error(capsys, None)


def test_muse_aspects_unknown_trigger(home, capsys):
    with pytest.raises(SystemExit) as exc:
        muse_aspects.main(["reward", "frobnicate", "did a thing"])
    assert exc.value.code == 2
    _assert_usage_error(capsys, None)


def test_morning_mirror_record_without_citation(home, capsys):
    with pytest.raises(SystemExit) as exc:
        morning_mirror.main(["record", "i am the storm that tends the hearth"])
    assert exc.value.code == 2
    _assert_usage_error(capsys, None)


def test_mythic_engineering_unknown_scroll(home, capsys):
    rc = mythic_engineering.main(["advance", "no-such-scroll", "SEIDR",
                                  "--note", "a sufficiently long note here"])
    assert rc == 2
    _assert_usage_error(capsys, None)


# valid paths still work -------------------------------------------------
def test_mood_work_start_valid(home, capsys):
    rc = mood_work.main(["start", "heavy", "--note",
                         "a sufficiently long honest note about the work"])
    assert rc == 0
    out, _ = capsys.readouterr()
    assert "work started" in out


def test_muse_aspects_reward_valid(home, capsys):
    muse_aspects.main(["reward", "tests_green", "suite is green"])
    out, _ = capsys.readouterr()
    assert "Reward recorded" in out
