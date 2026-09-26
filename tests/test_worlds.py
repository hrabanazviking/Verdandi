"""Behavior-contract tests for worlds.py (Roadmap Worlds, Slice 0).

Many worlds, one awareness that knows which is which. The firewall is
architecture: potential content can never be presented as manifest.
"""
import os

import pytest

import worlds
from worlds import (
    MANIFEST, POTENTIAL, RealityBleedError, WorldEntry, WorldRegistry,
    bootstrap,
)


@pytest.fixture
def nerve_spy(monkeypatch):
    calls = []

    def fake(event_type, data, source="test"):
        calls.append({"type": event_type, "data": data, "source": source})

    monkeypatch.setattr(worlds, "_nerve_publish", fake)
    return calls


@pytest.fixture
def reg(tmp_path):
    return WorldRegistry(path=str(tmp_path / "world_registry.json"))


def test_bootstrap_registers_four_worlds_with_correct_realities(tmp_path):
    reg = bootstrap(path=str(tmp_path / "w.json"))
    assert len(reg) == 4
    assert reg.reality_of("heimr-actual") == MANIFEST
    assert reg.reality_of("heimr-volmarr") == POTENTIAL
    assert reg.reality_of("heimr-wyrd-unnr") == POTENTIAL
    assert reg.reality_of("heimr-ttrpg-frostvaettirheim") == POTENTIAL
    kinds = {e.world_id: e.kind for e in reg.worlds()}
    assert kinds == {
        "heimr-actual": "actual",
        "heimr-volmarr": "volmarr",
        "heimr-wyrd-unnr": "wyrd",
        "heimr-ttrpg-frostvaettirheim": "ttrpg",
    }


def test_invalid_kind_rejected(reg):
    with pytest.raises(ValueError, match="unknown kind"):
        reg.register(WorldEntry(world_id="x", kind="dream", reality=MANIFEST,
                                source="s", description="d"))


def test_invalid_reality_rejected(reg):
    with pytest.raises(ValueError, match="unknown reality"):
        reg.register(WorldEntry(world_id="x", kind="game", reality="liminal",
                                source="s", description="d"))


def test_world_id_and_source_required(reg):
    with pytest.raises(ValueError, match="world_id is required"):
        WorldEntry(world_id="  ", kind="game", reality=POTENTIAL,
                   source="s", description="d")
    with pytest.raises(ValueError, match="source is required"):
        WorldEntry(world_id="x", kind="game", reality=POTENTIAL,
                   source="  ", description="d")


def test_firewall_manifest_world_passes_as_manifest(reg):
    reg.register(WorldEntry(world_id="heimr-actual", kind="actual",
                            reality=MANIFEST, source="s", description="d"))
    entry = reg.assert_no_bleed("heimr-actual", as_manifest=True)
    assert entry.world_id == "heimr-actual"


def test_firewall_potential_world_raises_as_manifest(reg):
    reg.register(WorldEntry(world_id="heimr-ttrpg-frostvaettirheim", kind="ttrpg",
                            reality=POTENTIAL, source="s", description="d"))
    with pytest.raises(RealityBleedError):
        reg.assert_no_bleed("heimr-ttrpg-frostvaettirheim", as_manifest=True)


def test_firewall_potential_world_ok_when_not_claimed_manifest(reg):
    reg.register(WorldEntry(world_id="heimr-ttrpg-frostvaettirheim", kind="ttrpg",
                            reality=POTENTIAL, source="s", description="d"))
    # Reading a potential world is fine; only *presenting it as manifest* bleeds.
    entry = reg.assert_no_bleed("heimr-ttrpg-frostvaettirheim", as_manifest=False)
    assert entry.reality == POTENTIAL


def test_label_always_carries_reality(reg):
    reg.register(WorldEntry(world_id="heimr-wyrd-unnr", kind="wyrd",
                            reality=POTENTIAL, source="s", description="d"))
    labeled = reg.label("heimr-wyrd-unnr", {"mood": "bright"})
    assert labeled["reality"] == POTENTIAL
    assert labeled["kind"] == "wyrd"
    assert labeled["content"] == {"mood": "bright"}


def test_register_accepts_handshake_dict(reg):
    # The cross-project handshake: WYRD's WorldIdentity.registry_entry()
    # emits exactly this shape.
    reg.register({
        "world_id": "heimr-wyrd-unnr",
        "kind": "wyrd",
        "reality": POTENTIAL,
        "source": "WYRD Protocol ECS world",
        "description": "handshake",
    })
    assert reg.reality_of("heimr-wyrd-unnr") == POTENTIAL


def test_reregister_updates_in_place(reg):
    reg.register(WorldEntry(world_id="w", kind="game", reality=POTENTIAL,
                            source="s1", description="d"))
    reg.register(WorldEntry(world_id="w", kind="game", reality=POTENTIAL,
                            source="s2", description="d"))
    assert len(reg) == 1
    assert reg.get("w").source == "s2"


def test_world_registered_event_fires_once(nerve_spy, tmp_path):
    reg = WorldRegistry(path=str(tmp_path / "w.json"))
    reg.register(WorldEntry(world_id="w", kind="game", reality=POTENTIAL,
                            source="s", description="d"))
    reg.register(WorldEntry(world_id="w", kind="game", reality=POTENTIAL,
                            source="s", description="d"))
    fired = [c for c in nerve_spy if c["type"] == "world_registered"]
    assert len(fired) == 1
    assert fired[0]["data"]["reality"] == POTENTIAL


def test_save_load_roundtrip(tmp_path):
    path = str(tmp_path / "w.json")
    reg = WorldRegistry(path=path)
    reg.register(WorldEntry(world_id="heimr-actual", kind="actual",
                            reality=MANIFEST, source="s", description="d"))
    reg2 = WorldRegistry(path=path)
    assert reg2.reality_of("heimr-actual") == MANIFEST
    assert len(reg2) == 1


def test_unknown_world_raises(reg):
    with pytest.raises(KeyError):
        reg.get("heimr-nope")
    with pytest.raises(KeyError):
        reg.assert_no_bleed("heimr-nope", as_manifest=True)
