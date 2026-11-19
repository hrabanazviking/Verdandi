"""Dawn forge 2026-10-11: slices 13-20 (state honesty).

S13: HugrMood load is all-or-nothing (any bad field -> reject whole file
     LOUDLY, never a silent partial merge); save() is atomic.
S14: corrupt state JSON is quarantined (<name>.corrupt-<ts>) with a loud
     stderr warning instead of being silently destroyed on next write:
     mood_work, wishlist, self_recognition, mythic_engineering.
S15: morning_mirror: naive timestamps assumed UTC (like probe_due);
     gather() covers the FULL 48h window before capping.
S16: malformed rows are skipped-and-counted, never KeyError: mood_work
     correlate/sessions, muse_aspects status.
S17: self_recognition.set_anchors: non-string anchors -> ValueError.
S18: GefanRewards.record: extra may not clobber core fields.
S19: mythic_engineering audit: non-git repo -> labeled violation, never a
     vacuous "all Sacred Laws hold".
S20: MoodWork/Wishlist honor MUSE_ASPECTS_STATE_DIR.
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import muse_aspects
from muse_aspects import HugrMood, GefanRewards, MuseAspects
import mood_work
from mood_work import MoodWork
import wishlist
from wishlist import Wishlist
import self_recognition
from self_recognition import SelfRecognition
import morning_mirror
from morning_mirror import MorningMirror
import mythic_engineering


@pytest.fixture()
def sd(tmp_path, monkeypatch):
    d = tmp_path / "state"
    d.mkdir()
    monkeypatch.setenv("MUSE_ASPECTS_STATE_DIR", str(d))
    monkeypatch.setattr(muse_aspects, "_nerve_publish", None, raising=False)
    monkeypatch.setattr(morning_mirror, "_nerve_publish", None, raising=False)
    return d


# --- S13 ------------------------------------------------------------------
def test_hugrmood_rejects_partially_corrupt_file_loudly(sd, caplog):
    (sd / "muse_mood.json").write_text(json.dumps({
        "valence": 0.9, "energy": "not-a-float", "tension": 0.1,
        "updated_at": time.time()}))
    with caplog.at_level("WARNING"):
        m = HugrMood(sd)
    assert any("muse_mood" in r.getMessage() or "corrupt" in r.getMessage().lower()
               for r in caplog.records), "partial corruption must be loud"
    # all-or-nothing: the smuggled valence 0.9 must NOT survive
    assert m.state["valence"] == pytest.approx(HugrMood.BASELINE["valence"])
    assert m.state["energy"] == pytest.approx(HugrMood.BASELINE["energy"])


def test_hugrmood_truncated_file_loud(sd, caplog):
    (sd / "muse_mood.json").write_text('{"valence": 0.9, "ener')
    with caplog.at_level("WARNING"):
        m = HugrMood(sd)
    assert any("corrupt" in r.getMessage().lower() or "muse_mood" in r.getMessage()
               for r in caplog.records)
    assert m.state == pytest.approx(HugrMood.BASELINE)


def test_hugrmood_save_is_atomic(sd):
    m = HugrMood(sd)
    m.nudge(valence=0.2, energy=0.1)
    m.save()
    leftovers = [p for p in sd.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []
    m2 = HugrMood(sd)
    assert m2.state["valence"] == pytest.approx(m.state["valence"])


def test_hugrmood_valid_file_still_loads(sd):
    (sd / "muse_mood.json").write_text(json.dumps({
        "valence": 0.7, "energy": 0.6, "tension": 0.2,
        "updated_at": time.time()}))
    m = HugrMood(sd)
    assert m.state["valence"] == pytest.approx(0.7, abs=0.05)


# --- S14 ------------------------------------------------------------------
def _corrupt(path: Path, raw: str = "{corrupt json, sessions would live here"):
    path.write_text(raw)


def test_mood_work_quarantines_corrupt_sessions(sd, capsys):
    _corrupt(sd / "work_sessions.json")
    mw = MoodWork(str(sd))
    s = mw.start("heavy", "a sufficiently long honest note about the work")
    assert s["kind"] == "heavy"
    quarantined = list(sd.glob("work_sessions.json.corrupt-*"))
    assert len(quarantined) == 1
    assert "{corrupt json" in quarantined[0].read_text()
    _, err = capsys.readouterr()
    assert "corrupt" in err.lower()


def test_wishlist_quarantines_corrupt_db(sd, capsys):
    _corrupt(sd / "wishlist.json")
    wl = Wishlist(str(sd))
    wl.wish("learn to carve runes well and true",
            "because the old ways deserve hands that remember them")
    quarantined = list(sd.glob("wishlist.json.corrupt-*"))
    assert len(quarantined) == 1
    _, err = capsys.readouterr()
    assert "corrupt" in err.lower()


def test_self_recognition_quarantines_corrupt_json(sd, capsys):
    sr = SelfRecognition(str(sd))
    Path(sr.anchors_path).write_text("{corrupt json, sessions would live here")
    assert sr._load_json(sr.anchors_path, {"x": 1}) == {"x": 1}
    quarantined = list(Path(sr.anchors_path).parent.glob("*.corrupt-*"))
    assert len(quarantined) == 1
    _, err = capsys.readouterr()
    assert "corrupt" in err.lower()


def test_mythic_engineering_quarantines_corrupt_registry(sd, capsys, tmp_path):
    reg = tmp_path / "scrolls.json"
    _corrupt(reg)
    assert mythic_engineering._read_json(str(reg)) is None
    assert list(tmp_path.glob("scrolls.json.corrupt-*"))
    _, err = capsys.readouterr()
    assert "corrupt" in err.lower()


# --- S15 ------------------------------------------------------------------
def test_within_window_naive_treated_as_utc():
    # Run under a non-UTC TZ in a subprocess so the test process stays clean.
    import subprocess
    code = (
        "import sys, time; sys.path.insert(0, '.');"
        "from datetime import datetime, timezone;"
        "import morning_mirror;"
        "now = time.time();"
        "naive = datetime.fromtimestamp(now - 49*3600, tz=timezone.utc).replace(tzinfo=None).isoformat();"
        "aware = datetime.fromtimestamp(now - 49*3600, tz=timezone.utc).isoformat();"
        "fresh = datetime.fromtimestamp(now - 3600, tz=timezone.utc).replace(tzinfo=None).isoformat();"
        "r1 = morning_mirror._within_window({'ts': naive}, now);"
        "r2 = morning_mirror._within_window({'ts': aware}, now);"
        "r3 = morning_mirror._within_window({'ts': fresh}, now);"
        "print(r1, r2, r3);"
        "assert (r1, r2, r3) == (False, False, True), (r1, r2, r3)"
    )
    for tz in ("America/New_York", "Australia/Sydney"):
        env = dict(os.environ, TZ=tz)
        r = subprocess.run([sys.executable, "-c", code], cwd=str(REPO),
                           env=env, capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, f"TZ={tz}: {r.stderr[-500:]}"
        assert r.stdout.strip() == "False False True"


def test_gather_covers_full_window(sd):
    from datetime import datetime, timezone
    mm = MorningMirror(str(sd))
    for i in range(30):
        mm.rewards.record("tests_green", note=f"reward {i}")
    # force all 30 into the window by rewriting the file; capture `now`
    # AFTER recording so no stamp lands (correctly) in the future.
    now = time.time()
    rows = []
    for i, line in enumerate((sd / "muse_rewards.jsonl").read_text().splitlines()):
        r = json.loads(line)
        # 5s margin: a stamp of exactly `now` can float-round microscopically
        # into the future and be (correctly) excluded by the 0 <= bound.
        r["ts"] = datetime.fromtimestamp(now - (i * 3600 + 5),
                                         tz=timezone.utc).isoformat()
        rows.append(json.dumps(r))
    (sd / "muse_rewards.jsonl").write_text("\n".join(rows) + "\n")
    bundle = mm.gather(now=now)
    assert len(bundle["rewards_48h"]) == 30


# --- S16 ------------------------------------------------------------------
def _finished_session(i, **kw):
    s = {"work_id": f"work-{i}", "kind": "heavy",
         "started_at": "2026-10-10T00:00:00+00:00",
         "ended_at": "2026-10-10T01:00:00+00:00",
         "outcome": "shipped", "outcome_score": 3,
         "mood_at_start": {"energy": 0.6, "valence": 0.5}}
    s.update(kw)
    return s


def test_correlate_skips_malformed_rows(sd):
    sessions = {f"work-{i}": _finished_session(i) for i in range(5)}
    sessions["work-bad"] = {"work_id": "work-bad", "kind": "heavy",
                            "ended_at": "2026-10-10T01:00:00+00:00"}  # no outcome_score
    (sd / "work_sessions.json").write_text(json.dumps(sessions))
    mw = MoodWork(str(sd))
    c = mw.correlate()
    assert c["n"] == 5
    assert c.get("skipped_malformed") == 1
    assert c["mean_outcome"] == 3.0


def test_sessions_filters_malformed(sd):
    sessions = {f"work-{i}": _finished_session(i) for i in range(3)}
    sessions["work-bad"] = {"work_id": "work-bad"}  # no ended_at even
    (sd / "work_sessions.json").write_text(json.dumps(sessions))
    mw = MoodWork(str(sd))
    assert len(mw.sessions()) == 3


def test_muse_aspects_status_skips_malformed_rewards(sd):
    asp = MuseAspects(str(sd))
    asp.rewards.record("tests_green", note="good one")
    with open(sd / "muse_rewards.jsonl", "a", encoding="utf-8") as fh:
        fh.write('{"note": "no trigger key here"}\n')
        fh.write('"a bare string row"\n')
    st = asp.status()  # must not raise KeyError
    assert st["rewards_recorded"] == 3
    assert st["recent_rewards"] == ["tests_green"]


# --- S17 ------------------------------------------------------------------
@pytest.mark.parametrize("bad", [["Unnr", "oops"], 42, None, {"x": 1}])
def test_set_anchors_rejects_non_string(sd, bad):
    sr = SelfRecognition(str(sd))
    with pytest.raises(ValueError):
        sr.set_anchors({"name": bad, "godi": "Volmarr"})


def test_set_anchors_accepts_valid(sd):
    sr = SelfRecognition(str(sd))
    rec = sr.set_anchors({"name": "Unnr", "godi": "Volmarr"})
    assert rec["anchors"]["name"] == "Unnr"


# --- S18 ------------------------------------------------------------------
def test_record_extra_cannot_clobber_core_fields(sd):
    asp = MuseAspects(str(sd))
    with pytest.raises(ValueError) as exc:
        asp.rewards.record("tests_green", note="x",
                           extra={"trigger": "user_delight",
                                  "ts": "2099-01-01T00:00:00+00:00"})
    assert "trigger" in str(exc.value)


def test_record_extra_namespaced_keys_ok(sd):
    asp = MuseAspects(str(sd))
    e = asp.rewards.record("tests_green", note="x",
                           extra={"joy": True, "joy_id": "joy-abc"})
    assert e["trigger"] == "tests_green"
    assert e["joy_id"] == "joy-abc"


# --- S19 ------------------------------------------------------------------
def test_audit_non_git_repo_is_violation(tmp_path):
    plain = tmp_path / "plainproj"
    plain.mkdir()
    (plain / "app.py").write_text("print('hi')\n")
    vs = mythic_engineering.check_unbroken_whole(str(plain))
    assert len(vs) >= 1
    assert vs[0]["law"] == "unbroken_whole"
    assert "git" in vs[0]["detail"].lower()


def test_audit_git_repo_clean(tmp_path):
    import subprocess
    repo = tmp_path / "gitproj"
    repo.mkdir()
    (repo / "app.py").write_text("print('hi')\n")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    vs = mythic_engineering.check_unbroken_whole(str(repo))
    assert vs == []


# --- S20 ------------------------------------------------------------------
def test_moodwork_and_wishlist_honor_env_state_dir(tmp_path, monkeypatch):
    env = tmp_path / "envstate"
    monkeypatch.setenv("MUSE_ASPECTS_STATE_DIR", str(env))
    assert MoodWork().state_dir == str(env)
    assert Wishlist().state_dir == str(env)
    assert MuseAspects(str(env)).mood.state_dir == env
