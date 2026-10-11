"""Dawn forge 2026-10-11: slices 6, 7, 8.

S6: wyrd_bridge must survive a garbage WYRD_BRIDGE_HORIZON_HOURS env value
    at import (warn + fall back to 24.0), never an import-time ValueError.
S7: wyrd_inbound.check_divergence must not die on a non-string mood claim.
S8: reality_audit must not die on wrong-shaped data: non-dict chapter
    lines in _manifest_sources, non-dict claims in check_stored_labels.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import wyrd_inbound
import reality_audit


# --- S6 -------------------------------------------------------------------
def test_bad_horizon_env_does_not_kill_import():
    env = dict(os.environ, WYRD_BRIDGE_HORIZON_HOURS="banana")
    r = subprocess.run(
        [sys.executable, "-c",
         "import wyrd_bridge; print(wyrd_bridge.HORIZON_HOURS)"],
        cwd=str(REPO), env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"import died: {r.stderr[-500:]}"
    assert r.stdout.strip() == "24.0"


def test_good_horizon_env_still_honored():
    env = dict(os.environ, WYRD_BRIDGE_HORIZON_HOURS="48")
    r = subprocess.run(
        [sys.executable, "-c",
         "import wyrd_bridge; print(wyrd_bridge.HORIZON_HOURS)"],
        cwd=str(REPO), env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
    assert r.stdout.strip() == "48.0"


# --- S7 -------------------------------------------------------------------
def test_check_divergence_survives_non_string_claims(tmp_path):
    proj = {
        "beliefs": [
            {"subject": "unnr:mood", "claim": {"not": "a string"}},
            {"subject": "unnr:mood", "claim": 42},
            {"subject": "unnr:mood", "claim": None},
            {"subject": "unnr:mood", "claim": "valence 0.50"},
        ]
    }
    mirror = tmp_path / "mirror.json"
    mirror.write_text(json.dumps(proj))
    out = wyrd_inbound.check_divergence(mirror_path=str(mirror),
                                        state_dir=str(tmp_path))
    assert isinstance(out, list)


# --- S8 -------------------------------------------------------------------
def test_manifest_sources_skips_non_dict_chapter_lines(tmp_path, capsys):
    cp = tmp_path / "autobiography_chapters.jsonl"
    cp.write_text(
        '{"title": "good", "text": "real chapter text"}\n'
        '"just a bare string line"\n'
        '42\n'
        '{"title": "also good", "text": "more text"}\n')
    out, skipped = reality_audit._manifest_sources(state_dir=str(tmp_path))
    assert skipped >= 2
    texts = [t for _, t in out]
    assert any("real chapter text" in t for t in texts)
    assert any("more text" in t for t in texts)
    _, err = capsys.readouterr()
    assert "skipping" in err.lower()


def test_check_stored_labels_survives_claims_as_list(tmp_path):
    (tmp_path / "volmarr_world.json").write_text(json.dumps({
        "claims": ["not", "a", "dict"],
    }))
    findings = reality_audit.check_stored_labels(state_dir=str(tmp_path))
    assert isinstance(findings, list)


def test_check_stored_labels_survives_non_dict_claim_values(tmp_path):
    (tmp_path / "volmarr_world.json").write_text(json.dumps({
        "claims": {"bravery": "a string, not a claim dict", "wisdom": 7},
    }))
    findings = reality_audit.check_stored_labels(state_dir=str(tmp_path))
    assert isinstance(findings, list)
