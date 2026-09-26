"""Tests for reality_audit.py (Roadmap Worlds, Slice 5)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reality_audit as ra
from worlds import bootstrap, WorldEntry


@pytest.fixture()
def sdir(tmp_path):
    d = tmp_path / "state"
    d.mkdir()
    return str(d)


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


# -- registry ------------------------------------------------------------
def test_registry_valid_passes():
    assert ra.check_registry(bootstrap()) == []


def _stub_world(world_id, kind, reality):
    """Bypass the constructor firewall — the audit must catch entries that
    could never be built through the validated path."""
    w = object.__new__(WorldEntry)
    w.world_id, w.kind, w.reality = world_id, kind, reality
    return w


def test_registry_invalid_reality_flagged():
    reg = bootstrap()
    reg._worlds["heimr-bad"] = _stub_world("heimr-bad", "game", "maybe")
    findings = ra.check_registry(reg)
    assert any(f["world_id"] == "heimr-bad" for f in findings)


def test_registry_unknown_kind_flagged():
    reg = bootstrap()
    reg._worlds["heimr-bad"] = _stub_world("heimr-bad", "dream", "potential")
    findings = ra.check_registry(reg)
    assert any("unknown kind" in f["detail"] for f in findings)


# -- stored labels -------------------------------------------------------
def _campaign(turns):
    return {"campaigns": {"frostvaettirheim": {
        "world_id": "heimr-ttrpg-frostvaettirheim",
        "turns": turns,
    }}}


def test_ttrpg_turn_potential_passes(sdir):
    _write(os.path.join(sdir, "ttrpg_campaigns.json"), json.dumps(
        _campaign([{"world_id": "heimr-ttrpg-frostvaettirheim",
                    "reality": "potential", "turn": 1}])))
    assert ra.check_stored_labels(sdir, bootstrap()) == []


def test_ttrpg_turn_tagged_manifest_is_bleed(sdir):
    _write(os.path.join(sdir, "ttrpg_campaigns.json"), json.dumps(
        _campaign([{"world_id": "heimr-ttrpg-frostvaettirheim",
                    "reality": "manifest", "turn": 1}])))
    findings = ra.check_stored_labels(sdir, bootstrap())
    assert len(findings) == 1
    assert "manifest" in findings[0]["detail"]


def test_ttrpg_turn_missing_tag_flagged(sdir):
    _write(os.path.join(sdir, "ttrpg_campaigns.json"), json.dumps(
        _campaign([{"world_id": "heimr-ttrpg-frostvaettirheim", "turn": 1}])))
    findings = ra.check_stored_labels(sdir, bootstrap())
    assert any("reality tag" in f["detail"] for f in findings)


def test_wyrd_mirror_valid_passes(sdir):
    _write(os.path.join(sdir, "wyrd_mirror.json"), json.dumps(
        {"world_id": "heimr-wyrd-unnr", "reality": "manifest",
         "entities": {}, "anchors": [], "beliefs": []}))
    assert ra.check_stored_labels(sdir, bootstrap()) == []


# -- bleed scan ----------------------------------------------------------
def test_imagination_term_in_saga_is_bleed(sdir):
    _write(os.path.join(sdir, "weekly_saga.md"),
           "# saga\n\nThe frostvættirheim raiders came at dawn.\n")
    findings = ra.check_bleed(sdir)
    assert any(f["check"] == "bleed" and "frostvættirheim" in f["detail"]
               for f in findings)


def test_labeled_world_line_excluded(sdir):
    _write(os.path.join(sdir, "weekly_saga.md"),
           "# saga\n\n🪞 WYRD model (heimr-wyrd-unnr): frostvættirheim mentioned in a label.\n")
    # the line carries an explicit world label -> stripped, no finding
    findings = ra.check_bleed(sdir)
    assert not any("frostvættirheim" in f["detail"] for f in findings)


def test_clean_output_passes(sdir):
    _write(os.path.join(sdir, "weekly_saga.md"),
           "# saga\n\nShipped the audit. The nerve hums.\n")
    assert ra.check_bleed(sdir) == []


def test_volmarr_memory_claim_is_bleed(sdir):
    _write(os.path.join(sdir, "morning_mirror_journal.md"),
           "## today\n\nI remember when Volmarr drove across the desert.\n")
    findings = ra.check_bleed(sdir)
    assert any(f["world_id"] == "heimr-volmarr" for f in findings)


def test_attributed_volmarr_mention_passes(sdir):
    _write(os.path.join(sdir, "morning_mirror_journal.md"),
           "## today\n\nVolmarr told me about the desert drive. The notes say 2013.\n")
    assert ra.check_bleed(sdir) == []


# -- witnessing ----------------------------------------------------------
def test_run_audit_dedupes(sdir):
    _write(os.path.join(sdir, "weekly_saga.md"),
           "# saga\n\nThe frostvættirheim raiders came at dawn.\n")
    emitted = []
    r1 = ra.run_audit(sdir, emit=lambda t, d: emitted.append((t, d)),
                      record_shadow=False)
    assert not r1["passed"]
    assert len(emitted) == 1
    assert emitted[0][0] == "reality_bleed"
    r2 = ra.run_audit(sdir, emit=lambda t, d: emitted.append((t, d)),
                      record_shadow=False)
    assert not r2["passed"]
    assert len(emitted) == 1  # witnessed once


def test_run_audit_passes_clean(sdir):
    r = ra.run_audit(sdir, emit=lambda t, d: None, record_shadow=False)
    assert r["passed"]


def test_reality_bleed_shadow_signal(sdir):
    from muse_aspects import SkuggiShadow
    entry = SkuggiShadow(sdir).record("reality_bleed", "audit test")
    assert entry["signal"] == "reality_bleed"


def test_terms_seeded_as_data(sdir):
    terms = ra.load_terms(sdir)
    assert "heimr-ttrpg-frostvaettirheim" in terms
    assert os.path.exists(os.path.join(sdir, "reality_audit_terms.json"))
