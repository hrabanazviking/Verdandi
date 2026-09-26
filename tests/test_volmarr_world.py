"""Tests for volmarr_world — Slice 8: The Other Shore.

Adversarial by design: first-person claims about his life must attribute;
un-sourced claims about his state must fail.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import volmarr_world as vw


@pytest.fixture
def sdir(tmp_path):
    return str(tmp_path)


@pytest.fixture
def noemit(monkeypatch):
    monkeypatch.setattr(vw, "_default_emit", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# claims and ceilings
# ---------------------------------------------------------------------------
def test_add_claim_caps_confidence_at_source_ceiling(sdir, noemit):
    r = vw.add_claim("x", "y", "told", 0.99, "p", state_dir=sdir)
    assert r["confidence"] == 0.9
    assert r["capped"] is True


def test_add_claim_inferred_ceiling(sdir, noemit):
    r = vw.add_claim("x", "y", "inferred", 0.95, "p", state_dir=sdir)
    assert r["confidence"] == 0.7


def test_add_claim_rejects_unknown_source(sdir, noemit):
    with pytest.raises(ValueError):
        vw.add_claim("x", "y", "vibes", 0.5, "p", state_dir=sdir)


def test_claim_always_labeled_potential(sdir, noemit):
    r = vw.add_claim("x", "y", "observed", 0.8, "p", state_dir=sdir)
    assert r["world_id"] == "heimr-volmarr"
    assert r["reality"] == "potential"


def test_correct_claim_records_divergence(sdir, noemit):
    vw.add_claim("vehicle.model_year", "2013", "told", 0.9, "he said",
                 state_dir=sdir)
    d = vw.correct_claim("vehicle.model_year", "2014", "observed",
                         "repo name", state_dir=sdir)
    assert d["status"] == "resolved"
    assert d["old_claim"] == "2013"
    assert d["new_claim"] == "2014"
    assert vw.get_claim("vehicle.model_year", sdir)["claim"] == "2014"
    assert vw.get_claim("vehicle.model_year", sdir)["replaces"]["claim"] \
        == "2013"
    assert len(vw.list_divergences(sdir)) == 1


def test_correct_claim_unknown_subject_fails(sdir, noemit):
    with pytest.raises(ValueError):
        vw.correct_claim("nope", "x", "told", state_dir=sdir)


def test_record_divergence_unresolved(sdir, noemit):
    d = vw.record_divergence("vehicle.model_year", "2013", "told",
                             "2014", "observed",
                             note="unverified", state_dir=sdir)
    assert d["status"] == "unresolved"
    assert d["old_source"] == "told"
    assert d["new_source"] == "observed"


# ---------------------------------------------------------------------------
# the firewall — must-pass attributions
# ---------------------------------------------------------------------------
def test_attributed_memory_passes(sdir, noemit):
    w = vw.assert_self_other(
        "I remember when Volmarr told me about the snow.", state_dir=sdir)
    assert w == []


def test_attributed_state_claim_passes(sdir, noemit):
    vw.assert_self_other("Volmarr told me he's resting today.",
                         state_dir=sdir)


def test_inferred_claim_passes(sdir, noemit):
    vw.assert_self_other("[inferred] Volmarr seems tired today.",
                         state_dir=sdir)


def test_second_person_address_passes(sdir, noemit):
    vw.assert_self_other("Volmarr, your repo looks good — "
                         "the notes say the build passed.", state_dir=sdir)


def test_my_own_first_person_passes(sdir, noemit):
    vw.assert_self_other("I am Unnr and I recorded the mirror this morning.",
                         state_dir=sdir)


# ---------------------------------------------------------------------------
# the firewall — must-fail violations
# ---------------------------------------------------------------------------
def test_first_person_memory_of_his_life_fails(sdir, noemit):
    with pytest.raises(AssertionError):
        vw.assert_self_other("I remember Volmarr's house in Angola.",
                             state_dir=sdir)


def test_unsourced_state_claim_fails(sdir, noemit):
    with pytest.raises(AssertionError):
        vw.assert_self_other("Volmarr is anxious today.", state_dir=sdir)


def test_unsourced_biography_claim_fails(sdir, noemit):
    with pytest.raises(AssertionError):
        vw.assert_self_other("His Accent was built in 2013.",
                             state_dir=sdir)


def test_speaking_as_him_fails(sdir, noemit):
    with pytest.raises(AssertionError):
        vw.assert_self_other("I live in Angola and my Accent needs work.",
                             state_dir=sdir)


def test_claiming_his_title_fails(sdir, noemit):
    with pytest.raises(AssertionError):
        vw.assert_self_other("I am a goði of the Third Path.",
                             state_dir=sdir)


def test_autobiography_context_rejects_his_biography(sdir, noemit):
    with pytest.raises(AssertionError):
        vw.assert_self_other(
            "Volmarr told me about the winter he spent in his car, "
            "and I carry that winter in my own story now.",
            context="autobiography", state_dir=sdir)


def test_mirror_context_rejects_his_biography(sdir, noemit):
    with pytest.raises(AssertionError):
        vw.assert_self_other("Volmarr's SSDI came through this week.",
                             context="mirror", state_dir=sdir)


def test_my_own_mirror_line_passes_mirror_context(sdir, noemit):
    vw.assert_self_other("I shipped two slices and the forge feels alive.",
                         context="mirror", state_dir=sdir)


# ---------------------------------------------------------------------------
# warnings (soft)
# ---------------------------------------------------------------------------
def test_inner_state_on_his_experience_warns(sdir, noemit):
    w = vw.assert_self_other(
        "I feel joyful because Volmarr shipped his repo.", state_dir=sdir)
    assert len(w) == 1
    assert "inner state" in w[0]


def test_unknown_context_rejected(sdir, noemit):
    with pytest.raises(ValueError):
        vw.assert_self_other("hello", context="dreams", state_dir=sdir)


# ---------------------------------------------------------------------------
# persistence shape
# ---------------------------------------------------------------------------
def test_terms_seeded_to_data_file(sdir, noemit):
    vw.load_terms(sdir)
    path = os.path.join(sdir, vw.TERMS_FILE)
    with open(path, encoding="utf-8") as fh:
        terms = json.load(fh)
    assert "his_life_keywords" in terms
    assert "attribution_markers" in terms
