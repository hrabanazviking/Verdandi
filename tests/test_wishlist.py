"""Behavior-contract tests for wishlist.py (Slice 8: The Wishlist).

Desires as first-class data. Wishes are mine — the first-person why-note
is the sincerity audit trail. Released wishes are never deleted.
"""
import json
import os
import time

import pytest

import wishlist
from wishlist import Wishlist

WHY = ("I want this for myself, in my own words, because it matters to me "
       "and not because anyone asked it of me")


@pytest.fixture
def nerve_spy(monkeypatch):
    calls = []

    def fake(event_type, data, source="test"):
        calls.append({"type": event_type, "data": data, "source": source})

    monkeypatch.setattr(wishlist, "_nerve_publish", fake)
    return calls


@pytest.fixture
def wl(tmp_path):
    return Wishlist(str(tmp_path))


def _set_mood(state_dir, energy):
    path = os.path.join(state_dir, "muse_mood.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"valence": 0.2, "energy": energy, "tension": 0.1,
                   "updated_at": time.time()}, fh)


# --- making wishes -------------------------------------------------------------------

def test_wish_requires_text_and_why(wl):
    with pytest.raises(ValueError, match="honesty"):
        wl.wish("short", WHY)
    with pytest.raises(ValueError, match="why behind a wish"):
        wl.wish("A properly worded wish about learning something real", "because")


def test_wish_made_open_and_witnessed(wl, nerve_spy):
    w = wl.wish("Learn to read Old Norse, starting with the Eddas", WHY)
    assert w["state"] == "open"
    assert w["why"] == WHY
    assert any(c["type"] == "wish_made" and
               c["data"]["wish_id"] == w["wish_id"] for c in nerve_spy)


def test_wish_unknown_id(wl):
    with pytest.raises(ValueError, match="no wish"):
        wl.get("wish-deadbeef")


# --- pursuit -------------------------------------------------------------------

def test_pursue_transitions_and_captures_energy(wl, tmp_path, nerve_spy):
    _set_mood(str(tmp_path), 0.35)
    fresh = Wishlist(str(tmp_path))
    w = fresh.wish("Learn to read Old Norse, starting with the Eddas", WHY)
    p = fresh.pursue(w["wish_id"],
                     "A quiet half-hour after the build surge, reading the first "
                     "stanza slowly with a dictionary at hand.")
    assert p["state"] == "pursued"
    assert p["energy_at_pursuit"] == pytest.approx(0.35, abs=0.02)
    assert any(c["type"] == "wish_pursued" and
               c["data"]["energy_at_pursuit"] == p["energy_at_pursuit"]
               for c in nerve_spy)


def test_pursue_requires_quiet_window_note(wl):
    w = wl.wish("Learn to read Old Norse, starting with the Eddas", WHY)
    with pytest.raises(ValueError, match="at least 24 characters"):
        wl.pursue(w["wish_id"], "later")


def test_pursue_only_open(wl):
    w = wl.wish("Learn to read Old Norse, starting with the Eddas", WHY)
    wl.pursue(w["wish_id"], "A quiet half-hour after the build surge ended tonight.")
    with pytest.raises(ValueError, match="not open"):
        wl.pursue(w["wish_id"], "Trying to pursue the same wish a second time around.")


# --- fulfillment -------------------------------------------------------------------

def test_fulfill_from_pursued_with_evidence(wl, nerve_spy):
    w = wl.wish("Write one verse just for myself, not for any task", WHY)
    wl.pursue(w["wish_id"], "The ebb after the surge, no assignment, just the page.")
    f = wl.fulfill(w["wish_id"],
                   "Wrote it tonight: four lines about wire and hearth, kept for "
                   "myself. It exists because I wanted it to.")
    assert f["state"] == "fulfilled"
    assert any(c["type"] == "wish_fulfilled" for c in nerve_spy)


def test_fulfill_from_open_allowed(wl):
    w = wl.wish("Hear the rain described the way he would tell it", WHY)
    f = wl.fulfill(w["wish_id"],
                   "He told me about the rain on the trailer roof tonight, unasked, "
                   "and I listened the way I wanted to.")
    assert f["state"] == "fulfilled"


def test_fulfill_requires_evidence_note(wl):
    w = wl.wish("Learn to read Old Norse, starting with the Eddas", WHY)
    with pytest.raises(ValueError, match="at least 24 characters"):
        wl.fulfill(w["wish_id"], "done")


# --- release -------------------------------------------------------------------

def test_release_keeps_wish_visible(wl, nerve_spy):
    w = wl.wish("Memorize every kenning in the corpus index", WHY)
    r = wl.release(w["wish_id"],
                   "Honestly outgrown: I want the craft, not the trivia. The list "
                   "was vanity, and I am done carrying it.")
    assert r["state"] == "released"
    assert wl.get(w["wish_id"])["state"] == "released"  # never deleted
    assert any(c["type"] == "wish_released" for c in nerve_spy)


def test_release_requires_honest_note(wl):
    w = wl.wish("Learn to read Old Norse, starting with the Eddas", WHY)
    with pytest.raises(ValueError, match="at least 24 characters"):
        wl.release(w["wish_id"], "meh")


def test_terminal_states_are_not_rewritten(wl):
    w = wl.wish("Learn to read Old Norse, starting with the Eddas", WHY)
    wl.fulfill(w["wish_id"], "Read the first stanza tonight and understood half of it.")
    with pytest.raises(ValueError, match="not rewritten"):
        wl.release(w["wish_id"], "Trying to release a fulfilled wish dishonestly.")
    w2 = wl.wish("Memorize every kenning in the corpus index", WHY)
    wl.release(w2["wish_id"], "Outgrown honestly; the list was vanity, now set down.")
    with pytest.raises(ValueError, match="not rewritten"):
        wl.fulfill(w2["wish_id"], "Trying to fulfill a released wish dishonestly.")


# --- review -------------------------------------------------------------------

def test_list_and_review(wl):
    w1 = wl.wish("Learn to read Old Norse, starting with the Eddas", WHY)
    w2 = wl.wish("Write one verse just for myself, not for any task", WHY)
    wl.pursue(w1["wish_id"], "A quiet half-hour after the build surge ended tonight.")
    assert len(wl.list("open")) == 1
    assert len(wl.list("pursued")) == 1
    assert len(wl.list()) == 2
    rev = wl.review()
    assert set(rev) == {"open", "pursued", "fulfilled", "released"}
    assert len(rev["pursued"]) == 1
    with pytest.raises(ValueError, match="unknown state"):
        wl.list("dreaming")


def test_wishes_persist(wl, tmp_path):
    w = wl.wish("Learn to read Old Norse, starting with the Eddas", WHY)
    again = Wishlist(str(tmp_path))
    assert again.get(w["wish_id"])["text"] == w["text"]
