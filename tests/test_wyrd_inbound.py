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
