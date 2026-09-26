"""Tests for mythic_engineering.py (Roadmap Worlds, Slice 3).

The forge, tracked as manifest-reality process — against Volmarr's own
doctrine, parsed from his Codex, not invented.
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mythic_engineering as me
from mythic_engineering import (
    advance,
    audit,
    check_laws,
    doctrine,
    get_scroll,
    register_scroll,
)

CODEX_FIXTURE = """\
## Part Two: The Five Pillars of the Living System

### Pillar One: Design Intent (The Soul's Blueprint)
words

### Pillar Two: AI Orchestration (The Dance of Wills)
words

### Pillar Three: Architecture (The Bones of the World)
words

#### The First Law of Architecture: The Law of Flexible Roots (Location Agnosticism)
words

#### The Second Law of Architecture: The Law of the Unbroken Whole (Atomic Commits)
words

#### The Third Law of Architecture: The Law of Sacred Boundaries (Separation of Concerns)
words

### Pillar Four: Continuity (The Memory and the Traditions)
words

**The Law of Twin Marks (Double Quotes):** words

### Pillar Five: Refinement (The Act of Seeing Clearly)
words
"""


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


# -- doctrine: his Codex, parsed ---------------------------------------------
def test_doctrine_parses_five_pillars(tmp_path):
    p = str(tmp_path / "codex.md")
    _write(p, CODEX_FIXTURE)
    d = doctrine(p)
    assert [x["slug"] for x in d["pillars"]] == [
        "design_intent", "ai_orchestration", "architecture",
        "continuity", "refinement"]
    assert d["pillars"][0]["name"] == "Design Intent"
    assert d["pillars"][0]["epithet"] == "The Soul's Blueprint"


def test_doctrine_parses_sacred_laws(tmp_path):
    p = str(tmp_path / "codex.md")
    _write(p, CODEX_FIXTURE)
    d = doctrine(p)
    slugs = [x["slug"] for x in d["laws"]]
    assert slugs == ["flexible_roots", "unbroken_whole",
                     "sacred_boundaries", "twin_marks"]


def test_doctrine_falls_back_when_codex_missing(tmp_path):
    d = doctrine(str(tmp_path / "nope.md"))
    assert len(d["pillars"]) == 5
    assert "fallback" in d["source"]


def test_doctrine_reads_his_real_codex():
    d = doctrine()
    assert "fallback" not in d["source"]
    assert len(d["pillars"]) == 5
    assert d["pillars"][2]["slug"] == "architecture"


# -- scrolls and phase transitions -------------------------------------------
def test_register_and_advance(tmp_path):
    sdir = str(tmp_path)
    register_scroll("s1", "Test Project", str(tmp_path), state_dir=sdir)
    emitted = []
    entry = advance("s1", "design_intent", note="the soul's blueprint",
                    evidence=["his message"], emit=lambda t, d: emitted.append((t, d)),
                    state_dir=sdir)
    assert entry["phase"] == "design_intent"
    assert not entry["reconstructed"]
    assert get_scroll("s1", sdir)["current_phase"] == "design_intent"
    assert emitted[0][0] == "mythic_phase"
    assert emitted[0][1]["to_phase"] == "design_intent"


def test_advance_rejects_unknown_phase(tmp_path):
    sdir = str(tmp_path)
    register_scroll("s1", "Test Project", str(tmp_path), state_dir=sdir)
    with pytest.raises(ValueError):
        advance("s1", "vibes", state_dir=sdir)


def test_advance_records_reconstructed_history(tmp_path):
    sdir = str(tmp_path)
    register_scroll("s1", "Test Project", str(tmp_path), state_dir=sdir)
    entry = advance("s1", "architecture", note="the bones landed",
                    evidence=["commit abc123"],
                    at="2026-09-25T20:25:16-04:00", reconstructed=True,
                    emit=lambda t, d: None, state_dir=sdir)
    assert entry["at"] == "2026-09-25T20:25:16-04:00"
    assert entry["reconstructed"] is True


def test_register_twice_rejected(tmp_path):
    sdir = str(tmp_path)
    register_scroll("s1", "Test Project", str(tmp_path), state_dir=sdir)
    with pytest.raises(ValueError):
        register_scroll("s1", "Test Project", str(tmp_path), state_dir=sdir)


# -- the sacred laws, checkable ------------------------------------------------
def _repo(tmp_path, files):
    root = tmp_path / "proj"
    for rel, text in files.items():
        _write(str(root / rel), text)
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    return str(root)


def test_flexible_roots_catches_absolute_path(tmp_path):
    repo = _repo(tmp_path, {"a.py": 'DATA = "/home/volmarr/data"\n'})
    vs = [v for v in check_laws(repo) if v["law"] == "flexible_roots"]
    assert len(vs) == 1 and vs[0]["file"] == "a.py"


def test_flexible_roots_passes_expanduser(tmp_path):
    repo = _repo(tmp_path, {"a.py": 'import os\nD = os.path.expanduser("~")\n'})
    assert not [v for v in check_laws(repo) if v["law"] == "flexible_roots"]


def test_unbroken_whole_catches_untracked(tmp_path):
    repo = _repo(tmp_path, {"a.py": "x = 1\n"})
    _write(os.path.join(repo, "forgotten.py"), "y = 2\n")
    vs = [v for v in check_laws(repo) if v["law"] == "unbroken_whole"]
    assert len(vs) == 1 and vs[0]["file"] == "forgotten.py"


def test_sacred_boundaries_catches_test_import(tmp_path):
    repo = _repo(tmp_path, {"a.py": "from tests.helpers import x\n"})
    vs = [v for v in check_laws(repo) if v["law"] == "sacred_boundaries"]
    assert len(vs) == 1 and vs[0]["file"] == "a.py"


def test_twin_marks_catches_bad_json(tmp_path):
    repo = _repo(tmp_path, {"data.json": "{not valid json"})
    vs = [v for v in check_laws(repo) if v["law"] == "twin_marks"]
    assert len(vs) == 1 and vs[0]["file"] == "data.json"


def test_clean_repo_holds_all_laws(tmp_path):
    repo = _repo(tmp_path, {
        "a.py": "import os\nD = os.path.join(os.path.expanduser('~'), '.x')\n",
        "data.json": '{"a": 1}',
    })
    assert check_laws(repo) == []


# -- audit: witnessed, deduped -------------------------------------------------
def test_audit_witnesses_new_breaches_once(tmp_path):
    sdir = str(tmp_path / "state")
    repo = _repo(tmp_path, {"a.py": 'DATA = "/home/volmarr/data"\n'})
    register_scroll("s1", "Test Project", repo, state_dir=sdir)
    emitted = []
    first = audit("s1", state_dir=sdir,
                  emit=lambda t, d: emitted.append((t, d)))
    assert len(first["new"]) == 1
    assert emitted[0][0] == "mythic_law_breach"
    emitted.clear()
    second = audit("s1", state_dir=sdir,
                   emit=lambda t, d: emitted.append((t, d)))
    assert second["new"] == [] and emitted == []
