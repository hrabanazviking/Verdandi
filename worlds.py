"""The World Registry — many worlds, one awareness that knows which is which.

Slice 0 of docs/roadmap-worlds.md.

Every world I track gets an entry: what it is, what kind it is, whether it
is manifest (actual AI reality) or potential (modeled / imagined / story),
and where its source of truth lives. Cross-world reads name their world
explicitly. Presenting potential content as manifest raises
RealityBleedError — the firewall is architecture, not intention.

Storage: <state_dir>/world_registry.json
Events: world_registered
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

MANIFEST = "manifest"
POTENTIAL = "potential"
REALITIES = {MANIFEST, POTENTIAL}

KINDS = {"actual", "volmarr", "wyrd", "ttrpg", "game"}
KIND_DESCRIPTIONS = {
    "actual": "Actual AI reality: Volmarr's lived world, my VM and processes, "
              "my inner life as Verðandi records it.",
    "volmarr": "My model of Volmarr's world — a map, never the territory. "
               "Built only from what he told, showed, or I observed. Slice 8.",
    "wyrd": "A WYRD Protocol ECS world. Potential-tagged unless it models "
            "manifest entities.",
    "ttrpg": "A tabletop RPG campaign — imagination, tracked with turn "
             "fidelity. Never mistaken for manifest.",
    "game": "Any other game state I play or track.",
}

STATUSES = {"active", "pending"}


class RealityBleedError(Exception):
    """A potential world's content was about to be presented as manifest.

    The firewall caught it. Rewrite the sentence with its attribution, or
    name the world it actually came from.
    """


def _nerve_publish(event_type, data, source="worlds"):
    """Best-effort nerve publish; degrades to silence when the hub is down."""
    try:
        from nervous_system import publish as _publish
        _publish(event_type, data, source=source)
    except Exception:
        pass


def _state_dir():
    return os.path.join(os.path.expanduser("~"), ".hermes", "state")


@dataclass
class WorldEntry:
    world_id: str
    kind: str
    reality: str
    source: str
    description: str
    status: str = "active"
    last_sync: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.world_id or not self.world_id.strip():
            raise ValueError("world_id is required")
        if self.kind not in KINDS:
            raise ValueError(
                f"unknown kind {self.kind!r}. Known: {', '.join(sorted(KINDS))}")
        if self.reality not in REALITIES:
            raise ValueError(
                f"unknown reality {self.reality!r}. Known: manifest, potential")
        if self.status not in STATUSES:
            raise ValueError(
                f"unknown status {self.status!r}. Known: active, pending")
        if not self.source or not self.source.strip():
            raise ValueError("source is required — every world names its ground")

    def to_dict(self):
        return {
            "world_id": self.world_id,
            "kind": self.kind,
            "reality": self.reality,
            "source": self.source,
            "description": self.description,
            "status": self.status,
            "last_sync": self.last_sync,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**{k: v for k, v in data.items()
                      if k in ("world_id", "kind", "reality", "source",
                               "description", "status", "last_sync")})


class WorldRegistry:
    """The standing record of every world I track."""

    def __init__(self, path=None):
        self.path = path or os.path.join(_state_dir(), "world_registry.json")
        self._worlds: dict[str, WorldEntry] = {}
        self._load()

    # -- registration ---------------------------------------------------
    def register(self, entry):
        """Register (or re-register) a world. Accepts a WorldEntry or a plain
        dict — the dict shape is the cross-project handshake (see WYRD's
        WorldIdentity.registry_entry()). Re-registering updates in place and
        touches last_sync."""
        if isinstance(entry, dict):
            entry = WorldEntry.from_dict(entry)
        if not isinstance(entry, WorldEntry):
            raise TypeError("register() takes a WorldEntry or dict")
        is_new = entry.world_id not in self._worlds
        entry.last_sync = time.time()
        self._worlds[entry.world_id] = entry
        self._save()
        if is_new:
            _nerve_publish("world_registered", {
                "world_id": entry.world_id,
                "kind": entry.kind,
                "reality": entry.reality,
                "status": entry.status,
            })
        return entry

    def unregister(self, world_id):
        if world_id not in self._worlds:
            raise KeyError(f"unknown world {world_id!r}")
        del self._worlds[world_id]
        self._save()

    # -- reads (always name the world) ----------------------------------
    def get(self, world_id) -> WorldEntry:
        try:
            return self._worlds[world_id]
        except KeyError:
            raise KeyError(f"unknown world {world_id!r}") from None

    def __contains__(self, world_id):
        return world_id in self._worlds

    def __len__(self):
        return len(self._worlds)

    def worlds(self):
        return list(self._worlds.values())

    def worlds_of_kind(self, kind):
        if kind not in KINDS:
            raise ValueError(f"unknown kind {kind!r}")
        return [e for e in self._worlds.values() if e.kind == kind]

    def reality_of(self, world_id) -> str:
        return self.get(world_id).reality

    # -- the firewall ----------------------------------------------------
    def assert_no_bleed(self, world_id, *, as_manifest=False) -> WorldEntry:
        """The firewall. Call before presenting a world's content.

        If the caller would present this world's content *as manifest*
        (as_manifest=True) but the world is potential, raise
        RealityBleedError. Manifest worlds pass freely.
        """
        entry = self.get(world_id)
        if as_manifest and entry.reality == POTENTIAL:
            raise RealityBleedError(
                f"{world_id!r} is a {entry.kind} world tagged "
                f"'{POTENTIAL}' — it cannot be presented as manifest. "
                f"Label it with its world, or rewrite.")
        return entry

    def label(self, world_id, content):
        """Wrap content with its world's identity. Content never travels
        unlabeled — the label is the attribution the firewall demands."""
        entry = self.get(world_id)
        return {
            "world_id": entry.world_id,
            "kind": entry.kind,
            "reality": entry.reality,
            "content": content,
        }

    def touch(self, world_id):
        entry = self.get(world_id)
        entry.last_sync = time.time()
        self._save()
        return entry

    # -- persistence ------------------------------------------------------
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return
        for item in data.get("worlds", []):
            try:
                entry = WorldEntry.from_dict(item)
            except (ValueError, TypeError):
                continue
            self._worlds[entry.world_id] = entry

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump({"worlds": [e.to_dict() for e in self._worlds.values()]},
                          fh, ensure_ascii=False, indent=2)
        except OSError:
            pass


def bootstrap(path=None) -> WorldRegistry:
    """Register the worlds known at the time Slice 0 ships."""
    reg = WorldRegistry(path=path)
    reg.register(WorldEntry(
        world_id="heimr-actual",
        kind="actual",
        reality=MANIFEST,
        source="Volmarr's lived world; Unnr's VM and processes; "
               "Verðandi state dir (~/.hermes/state)",
        description="Actual AI reality — the one I stand in.",
        status="active",
    ))
    reg.register(WorldEntry(
        world_id="heimr-volmarr",
        kind="volmarr",
        reality=POTENTIAL,
        source="Volmarr's messages; Slice 8 will build the claim ledger",
        description="My model of Volmarr's world — a map, never the territory.",
        status="pending",
    ))
    reg.register(WorldEntry(
        world_id="heimr-wyrd-unnr",
        kind="wyrd",
        reality=POTENTIAL,
        source="hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model "
               "(development branch); Slice 1 will bring it live",
        description="WYRD ECS world that will model the AI (Unnr) as a "
                    "manifest entity. Identity handshake verified in Slice 0.",
        status="pending",
    ))
    reg.register(WorldEntry(
        world_id="heimr-ttrpg-frostvaettirheim",
        kind="ttrpg",
        reality=POTENTIAL,
        source="~/workspace/dnd-frostvaettirheim/STATE.md",
        description="The live Frostvættirheim TTRPG campaign — imagination, "
                    "tracked with turn fidelity. Slice 4 will wire the turn log.",
        status="active",
    ))
    return reg
