"""Tests for ttrpg.py (Roadmap Worlds, Slice 4).

The table, tracked as imagination — with full turn fidelity.
"""
import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ttrpg
from ttrpg import (
    engine_roll,
    get_baseline,
    get_log,
    import_baseline,
    record_turn,
    register_campaign,
)

STATE_FIXTURE = """\
# Campaign State — Test Saga

## Party
- **Test Hero** — Level 3 Fighter, HP 28/28, AC 15.

## Current Scene
A snowy bridge at dusk. Three shapes approach.

## Open Threads
- Who are the shapes?
- The bridge toll: unpaid.

## Last Player Move
Test Hero raised a shield (2026-01-01).
"""

WORLD = "heimr-ttrpg-frostvaettirheim"


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _reg(sdir):
    return register_campaign("test-saga", "Test Saga", WORLD, state_dir=sdir)


# -- campaigns ---------------------------------------------------------------
def test_register_campaign(tmp_path):
    sdir = str(tmp_path)
    c = _reg(sdir)
    assert c["world_id"] == WORLD
    with pytest.raises(ValueError):
        register_campaign("test-saga", "Test Saga", WORLD, state_dir=sdir)


def test_register_refuses_manifest_world(tmp_path):
    sdir = str(tmp_path)
    with pytest.raises(ValueError):
        register_campaign("bad", "Bad", "heimr-actual", state_dir=sdir)


# -- baseline ----------------------------------------------------------------
def test_import_baseline_labels_potential(tmp_path):
    sdir = str(tmp_path)
    _reg(sdir)
    md = str(tmp_path / "STATE.md")
    _write(md, STATE_FIXTURE)
    b = import_baseline("test-saga", md, state_dir=sdir)
    assert b["world_id"] == WORLD
    assert b["reality"] == "potential"
    sections = b["content"]["sections"]
    assert "Party" in sections and "Current Scene" in sections
    assert "Open Threads" in sections and "Last Player Move" in sections
    assert "Test Hero" in sections["Party"]


def test_get_baseline_roundtrip(tmp_path):
    sdir = str(tmp_path)
    _reg(sdir)
    md = str(tmp_path / "STATE.md")
    _write(md, STATE_FIXTURE)
    import_baseline("test-saga", md, state_dir=sdir)
    assert get_baseline("test-saga", sdir)["reality"] == "potential"


# -- turns -------------------------------------------------------------------
def test_record_turn_uses_engine_roll(tmp_path, monkeypatch):
    sdir = str(tmp_path)
    _reg(sdir)
    monkeypatch.setattr(
        ttrpg, "engine_roll",
        lambda expr, **k: {"expression": expr, "total": 17,
                           "breakdown": "[17]", "source": "dnd-engine"})
    emitted = []
    t = record_turn("test-saga", actor="Test Hero", action="swings sword",
                    scene="snowy bridge", roll_expression="1d20+5",
                    outcome="hits", threads_updated=["shapes"],
                    emit=lambda et, d: emitted.append((et, d)),
                    state_dir=sdir)
    c = t["content"]
    assert c["n"] == 1
    assert c["roll"]["total"] == 17 and c["roll"]["source"] == "dnd-engine"
    assert t["reality"] == "potential"
    assert emitted[0][0] == "ttrpg_turn"


def test_turns_number_sequentially(tmp_path, monkeypatch):
    sdir = str(tmp_path)
    _reg(sdir)
    monkeypatch.setattr(ttrpg, "engine_roll",
                        lambda expr, **k: {"expression": expr, "total": 1,
                                           "breakdown": "[1]",
                                           "source": "dnd-engine"})
    record_turn("test-saga", actor="A", action="a", roll_expression="1d20",
                emit=lambda et, d: None, state_dir=sdir)
    t2 = record_turn("test-saga", actor="A", action="b",
                     emit=lambda et, d: None, state_dir=sdir)
    assert t2["content"]["n"] == 2


def test_imported_history_keeps_documented_roll(tmp_path):
    sdir = str(tmp_path)
    _reg(sdir)
    t = record_turn(
        "test-saga", actor="Goblin", action="looses arrow",
        roll={"expression": "1d20+4", "total": 16, "breakdown": "[12]+4",
              "source": "dnd-engine (session record)"},
        outcome="arrow bends in the radiance",
        at="2026-09-24T15:15:00-04:00",
        provenance={"imported_from": "STATE.md", "reconstructed": True},
        emit=lambda et, d: None, state_dir=sdir)
    c = t["content"]
    assert c["roll"]["total"] == 16
    assert c["provenance"]["imported_from"] == "STATE.md"


def test_every_log_entry_is_potential(tmp_path, monkeypatch):
    sdir = str(tmp_path)
    _reg(sdir)
    monkeypatch.setattr(ttrpg, "engine_roll",
                        lambda expr, **k: {"expression": expr, "total": 1,
                                           "breakdown": "[1]",
                                           "source": "dnd-engine"})
    record_turn("test-saga", actor="A", action="a", roll_expression="1d20",
                emit=lambda et, d: None, state_dir=sdir)
    for t in get_log("test-saga", sdir):
        assert t["reality"] == "potential"
        assert t["world_id"] == WORLD


def test_record_turn_rejects_both_roll_forms(tmp_path):
    sdir = str(tmp_path)
    _reg(sdir)
    with pytest.raises(ValueError):
        record_turn("test-saga", actor="A", action="a",
                    roll_expression="1d20", roll={"total": 5},
                    emit=lambda et, d: None, state_dir=sdir)


# -- the engine, mechanical ----------------------------------------------------
def test_engine_roll_is_mechanical():
    if not os.path.exists(ttrpg.ENGINE_PYTHON):
        pytest.skip("dnd-engine venv not present")
    r = engine_roll("1d20+4")
    assert r["source"] == "dnd-engine"
    assert r["expression"] == "1d20+4"
    assert 5 <= r["total"] <= 24
    assert r["breakdown"]
