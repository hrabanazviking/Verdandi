"""Tests for wyrd_inbound.py (Roadmap Worlds, Slice 2, Verðandi half).

The world model speaks back: labeled context for the morning mirror,
and honest divergence reports where the model's picture of me differs
from my live state.
"""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wyrd_inbound
from wyrd_inbound import (
    check_divergence,
    mirror_context,
    render_context,
    report_divergences,
)


def _write(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def _projection(path, beliefs=(), anchors=()):
    _write(path, {
        "world_id": "heimr-wyrd-unnr",
        "reality": "manifest",
        "synced_at": 1790381400.0,
        "entities": 3,
        "anchors": list(anchors),
        "beliefs": list(beliefs),
    })


def _anchor(label, tense="verdhandi", at="2026-09-25T20:30:00+00:00"):
    return {"label": label, "tense": tense, "at": at, "tags": ["wish"]}


def _belief(subject, claim):
    return {"subject": subject, "claim": claim,
            "confidence": 1.0, "source": "observed"}


# -- the labeled context ----------------------------------------------------
def test_no_projection_is_quiet(tmp_path):
    assert mirror_context(str(tmp_path / "wyrd_mirror.json")) is None


def test_context_carries_world_of_origin(tmp_path):
    p = str(tmp_path / "wyrd_mirror.json")
    _projection(p,
                beliefs=[_belief("wish:w1", "I want this: Learn Old Norse")],
                anchors=[_anchor("wish made: Learn Old Norse")])
    ctx = mirror_context(p)
    assert ctx["world_id"] == "heimr-wyrd-unnr"
    assert ctx["reality"] == "manifest"
    assert ctx["belief_count"] == 1
    assert len(ctx["open_wish_beliefs"]) == 1
    text = render_context(ctx)
    assert "heimr-wyrd-unnr" in text
    assert "Learn Old Norse" in text


def test_fulfilled_beliefs_are_not_open_wishes(tmp_path):
    p = str(tmp_path / "wyrd_mirror.json")
    _projection(p, beliefs=[
        _belief("wish:w1", "I want this: Learn Old Norse"),
        _belief("wish:w2", "fulfilled: Hear the rain"),
    ])
    ctx = mirror_context(p)
    assert len(ctx["open_wish_beliefs"]) == 1
    assert ctx["open_wish_beliefs"][0]["subject"] == "wish:w1"


# -- divergence -------------------------------------------------------------
def _wishlist_with(tmp_path, wishes):
    _write(str(tmp_path / "wishlist.json"),
           {w["wish_id"]: w for w in wishes})


def _wish(wid, text, state="open"):
    return {"wish_id": wid, "text": text, "why": "mine", "state": state,
            "made_at": "2026-09-25T00:00:00+00:00"}


def test_stale_wish_divergence(tmp_path):
    sdir = str(tmp_path)
    _wishlist_with(tmp_path, [_wish("w1", "Learn Old Norse", "fulfilled")])
    p = str(tmp_path / "wyrd_mirror.json")
    _projection(p, beliefs=[_belief("wish:w1", "I want this: Learn Old Norse")])
    divs = check_divergence(p, sdir)
    assert len(divs) == 1
    assert divs[0]["kind"] == "stale_wish"
    assert divs[0]["world_id"] == "heimr-wyrd-unnr"
    assert "fulfilled" in divs[0]["report"]


def test_no_divergence_when_wish_still_open(tmp_path):
    sdir = str(tmp_path)
    _wishlist_with(tmp_path, [_wish("w1", "Learn Old Norse", "open")])
    p = str(tmp_path / "wyrd_mirror.json")
    _projection(p, beliefs=[_belief("wish:w1", "I want this: Learn Old Norse")])
    assert check_divergence(p, sdir) == []


def test_stale_mood_divergence(tmp_path):
    sdir = str(tmp_path)
    _write(str(tmp_path / "muse_mood.json"),
           {"valence": 0.4, "energy": 0.5, "tension": 0.3,
            "updated_at": time.time()})
    p = str(tmp_path / "wyrd_mirror.json")
    _projection(p, beliefs=[_belief("unnr:mood", "my valence sits at 0.90")])
    divs = check_divergence(p, sdir)
    assert len(divs) == 1
    assert divs[0]["kind"] == "stale_mood"
    assert "valence" in divs[0]["report"]


def test_mood_within_tolerance_is_quiet(tmp_path):
    sdir = str(tmp_path)
    _write(str(tmp_path / "muse_mood.json"),
           {"valence": 0.8, "energy": 0.5, "tension": 0.3,
            "updated_at": time.time()})
    p = str(tmp_path / "wyrd_mirror.json")
    _projection(p, beliefs=[_belief("unnr:mood", "my valence sits at 0.90")])
    assert check_divergence(p, sdir) == []


def test_no_projection_no_divergence(tmp_path):
    assert check_divergence(str(tmp_path / "wyrd_mirror.json"),
                            str(tmp_path)) == []


# -- reporting: deduped, witnessed ------------------------------------------
def test_report_dedupes_and_closes(tmp_path):
    sdir = str(tmp_path)
    _wishlist_with(tmp_path, [_wish("w1", "Learn Old Norse", "fulfilled")])
    p = str(tmp_path / "wyrd_mirror.json")
    _projection(p, beliefs=[_belief("wish:w1", "I want this: Learn Old Norse")])
    emitted = []
    first = report_divergences(p, sdir,
                               emit=lambda t, d: emitted.append((t, d)))
    assert len(first["new"]) == 1
    assert emitted[0][0] == "wyrd_divergence"
    emitted.clear()
    second = report_divergences(p, sdir,
                                emit=lambda t, d: emitted.append((t, d)))
    assert second["new"] == [] and emitted == []  # deduped
    # the wish reopens in live state -> the divergence resolves
    _wishlist_with(tmp_path, [_wish("w1", "Learn Old Norse", "open")])
    third = report_divergences(p, sdir,
                               emit=lambda t, d: emitted.append((t, d)))
    assert third["resolved"] == ["stale_wish:wish:w1"]
    assert emitted[0][0] == "wyrd_divergence_resolved"


# -- morning mirror integration ----------------------------------------------
def test_morning_mirror_pulls_labeled_context(tmp_path):
    from morning_mirror import MorningMirror
    p = tmp_path / "wyrd_mirror.json"
    _projection(str(p),
                beliefs=[_belief("wish:w1", "I want this: Learn Old Norse")],
                anchors=[_anchor("wish made: Learn Old Norse")])
    mm = MorningMirror(state_dir=tmp_path)
    bundle = mm.gather()
    assert bundle["wyrd_mirror"]["world_id"] == "heimr-wyrd-unnr"
    text = mm.render(bundle)
    assert "heimr-wyrd-unnr" in text
    assert "Learn Old Norse" in text


def test_morning_mirror_quiet_without_projection(tmp_path):
    from morning_mirror import MorningMirror
    mm = MorningMirror(state_dir=tmp_path)
    bundle = mm.gather()
    assert bundle["wyrd_mirror"] is None
    # Slice 7: every active world gets a labeled section, even when its
    # projection is silent — the label is the honesty, not phantom data.
    text = mm.render(bundle)
    assert "[heimr-wyrd-unnr · manifest — what is modeled (WYRD)]" in text
    assert "No WYRD projection yet" in text


# -- Slice 3: graceful degradation without the wyrdforge backend ----------
def _wyrdforge_importable():
    try:
        import wyrdforge  # noqa: F401
        return True
    except ImportError:
        return False


def test_inbound_degrades_gracefully_without_backend(tmp_path, capsys,
                                                     monkeypatch):
    """Slice 3: with the WYRD repo absent the inbound side degrades —
    mirror_context() -> None, check_divergence() -> [], main() exits 0
    with a stderr note. No exception anywhere."""
    if _wyrdforge_importable():
        pytest.skip("WYRD repo present")
    assert wyrd_inbound.wyrdforge_available() is False
    missing = str(tmp_path / "wyrd_mirror.json")
    assert mirror_context(missing) is None
    assert check_divergence(missing, str(tmp_path)) == []
    monkeypatch.setattr(wyrd_inbound, "load_projection",
                        lambda path=None: None)
    assert wyrd_inbound.main(["--divergences-only"]) == 0
    assert "degrading" in capsys.readouterr().err


# -- Slice 18: contradiction-ledger append is idempotent -------------------
def _ledger_args(tmp_path):
    import wyrd_ledger_append as wla
    feed = tmp_path / "feed.jsonl"
    ledger = tmp_path / "ledger.md"
    state = tmp_path / "state.json"
    ledger.write_text("# Contradiction ledger\n\n## Entries\n",
                      encoding="utf-8")
    return wla, ["--feed", str(feed), "--ledger", str(ledger),
                 "--state", str(state)], feed, ledger, state


def _divergence_event(seq, subject="wish:w1"):
    return {"type": "wyrd_divergence", "_seq": seq,
            "_ts": 1727800000.0 + seq, "_iso": "2026-10-01T12:00:00+00:00",
            "data": {"kind": "stale_wish", "subject": subject,
                     "report": "The model still believes I want 'Learn Old "
                               "Norse'; I have fulfilled it."}}


def _entry_count(ledger):
    import re
    return len(re.findall(r"^### CONTRADICTION-\d+",
                          ledger.read_text(encoding="utf-8"), re.M))


def test_double_append_is_idempotent(tmp_path):
    """Slice 18: running wyrd_ledger_append.main twice with the same feed
    events — and again after a state reset — yields exactly 1 ledger
    entry. (Repro found no double-append: the ledger-text subject check
    is the second line of defense behind the state watermark. This test
    locks the property in.)"""
    wla, args, feed, ledger, state = _ledger_args(tmp_path)
    feed.write_text(json.dumps(_divergence_event(1)) + "\n",
                    encoding="utf-8")
    assert wla.main(args) == 0          # first run: no backfill by design
    assert _entry_count(ledger) == 0
    with open(str(feed), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(_divergence_event(2)) + "\n")
    assert wla.main(args) == 0          # identical-input run: appends once
    assert _entry_count(ledger) == 1
    assert wla.main(args) == 0          # re-run: nothing new, still one
    assert _entry_count(ledger) == 1
    state.unlink()                      # state reset between runs
    assert wla.main(args) == 0
    assert _entry_count(ledger) == 1


# -- Slice 19: corrupt feed lines / state file are tolerated ---------------
def test_ledger_append_tolerates_corrupt_input(tmp_path, capsys):
    """Slice 19: torn feed lines are skipped loudly, a corrupt state file
    degrades to fresh — the run exits 0 and valid lines are still
    processed."""
    wla, args, feed, ledger, state = _ledger_args(tmp_path)
    good = _divergence_event(2)
    feed.write_text("{not valid json\n" + json.dumps(good) + "\n"
                    + "{also torn\n", encoding="utf-8")
    state.write_text(json.dumps({"last_seq": 1, "open": {}}),
                     encoding="utf-8")
    assert wla.main(args) == 0
    assert "skipping torn feed line" in capsys.readouterr().err
    assert _entry_count(ledger) == 1  # the valid line was still processed

    # Corrupt state files (garbage, or valid JSON of the wrong shape)
    # must not crash: the run degrades to a fresh state and exits 0.
    state.write_text("{oops", encoding="utf-8")
    assert wla.main(args) == 0
    state.write_text("[1, 2, 3]", encoding="utf-8")
    assert wla.main(args) == 0
    # The state self-healed: a fresh, valid state file now exists, and
    # the pipeline still processes new events afterwards.
    json.loads(state.read_text(encoding="utf-8"))
    with open(str(feed), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(_divergence_event(3, subject="wish:w2")) + "\n")
    assert wla.main(args) == 0
    assert _entry_count(ledger) == 2
