"""Tests for wyrd_bridge.py (Roadmap Worlds, Slice 1, Verðandi half).

The runner projects the nerve feed into the WYRD mirror world, stays
silent when nothing is new, and witnesses real syncs on the nerve.
"""
import json
import os
import sys

import pytest

# The runner imports wyrdforge from the WYRD repo — same as production.
WYRD_SRC = os.path.join(os.path.expanduser("~"), "workspace", "repos",
                        "WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model",
                        "src")
if WYRD_SRC not in sys.path:
    sys.path.insert(0, WYRD_SRC)

import wyrd_bridge
from wyrd_bridge import run


def _write_feed(path, entries):
    with open(path, "w", encoding="utf-8") as fh:
        for i, (etype, data) in enumerate(entries, start=1):
            fh.write(json.dumps({"type": etype, "data": data,
                                 "_seq": i, "_ts": 1790381094.0 + i}) + "\n")


@pytest.fixture
def paths(tmp_path):
    return {
        "feed_path": str(tmp_path / "nerve_feed.jsonl"),
        "cursor_path": str(tmp_path / "cursor.json"),
        "mirror_path": str(tmp_path / "wyrd_mirror.json"),
        "registry_path": str(tmp_path / "registry.json"),
    }


def test_sync_maps_mood_and_wish(paths):
    _write_feed(paths["feed_path"], [
        ("ping", {}),
        ("mood_shift", {"after": {"valence": 0.8, "energy": 0.7},
                        "why": "shipped slice 1"}),
        ("wish_made", {"wish_id": "w1", "text": "Learn Old Norse",
                       "why": "mine"}),
    ])
    emitted = []
    result = run(emit=lambda t, d: emitted.append((t, d)), **paths)
    assert result["changed"] is True
    summary = result["summary"]
    assert summary["world_id"] == "heimr-wyrd-unnr"
    assert summary["reality"] == "manifest"
    assert len(summary["anchors"]) == 2
    assert len(summary["beliefs"]) == 2  # mood belief + wish belief
    assert len(emitted) == 1
    assert emitted[0][0] == "wyrd_mirror_synced"
    assert emitted[0][1]["new_events"] == 2
    # durable projection written
    with open(paths["mirror_path"], encoding="utf-8") as fh:
        mirror = json.load(fh)
    assert mirror["world_id"] == "heimr-wyrd-unnr"


def test_registry_flips_to_manifest_active(paths):
    _write_feed(paths["feed_path"], [
        ("wish_made", {"wish_id": "w1", "text": "t"}),
    ])
    run(emit=lambda t, d: None, **paths)
    import worlds
    reg = worlds.WorldRegistry(path=paths["registry_path"])
    entry = reg.get("heimr-wyrd-unnr")
    assert entry.reality == "manifest"
    assert entry.status == "active"


def test_silent_when_nothing_new(paths):
    _write_feed(paths["feed_path"], [
        ("wish_made", {"wish_id": "w1", "text": "t"}),
    ])
    emitted = []
    first = run(emit=lambda t, d: emitted.append((t, d)), **paths)
    assert first["changed"] is True
    emitted.clear()
    second = run(emit=lambda t, d: emitted.append((t, d)), **paths)
    assert second["changed"] is False
    assert emitted == []


def test_unmapped_events_advance_cursor_but_stay_silent(paths):
    _write_feed(paths["feed_path"], [("ping", {}), ("ping", {})])
    emitted = []
    result = run(emit=lambda t, d: emitted.append((t, d)), **paths)
    assert result["changed"] is False
    assert emitted == []
    with open(paths["cursor_path"], encoding="utf-8") as fh:
        assert json.load(fh)["last_seq"] == 2


def test_missing_feed_is_quiet(paths):
    emitted = []
    result = run(emit=lambda t, d: emitted.append((t, d)), **paths)
    assert result["changed"] is False
    assert emitted == []
