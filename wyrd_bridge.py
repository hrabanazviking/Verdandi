"""wyrd_bridge — Verðandi → WYRD outbound runner (Roadmap Worlds, Slice 1).

Reads the nerve feed, projects it into the WYRD mirror world
(``heimr-wyrd-unnr``) via wyrdforge.bridges.verdandi_bridge, and witnesses
the sync back on the nerve.

The mirror world is a pure projection of the feed: every run replays the
whole feed into a fresh world, so there is no snapshot to drift. A cursor
(last processed nerve _seq) keeps the runner quiet when nothing is new —
``wyrd_mirror_synced`` is published only when mapped events were applied.

Each sync also re-registers the world's identity (manifest/active) in the
World Registry and writes a plain-data projection to wyrd_mirror.json for
Slice 2's inbound bridge.

Usage:  python wyrd_bridge.py
"""
from __future__ import annotations

import json
import os
import sys
import time

WYRD_REPO = os.environ.get(
    "WYRD_REPO",
    os.path.join(os.path.expanduser("~"), "workspace", "repos",
                 "WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model"))


def _state_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".hermes", "state")


def _default_emit(event_type: str, data: dict) -> None:
    try:
        from nervous_system import publish_event_sync as _publish
        _publish(event_type, data, "wyrd_bridge")
    except Exception:
        pass


def _load_wyrdforge():
    src = os.path.join(WYRD_REPO, "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from wyrdforge.bridges.verdandi_bridge import VerdandiBridge
    return VerdandiBridge


def _read_jsonl(path: str) -> list[dict]:
    entries = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    return entries


def _read_cursor(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as fh:
            return int(json.load(fh).get("last_seq", 0))
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return 0


def _write_cursor(path: str, last_seq: int) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"last_seq": last_seq}, fh)
    except OSError:
        pass


def run(feed_path: str | None = None,
        cursor_path: str | None = None,
        mirror_path: str | None = None,
        registry_path: str | None = None,
        emit=None) -> dict:
    """Sync the mirror world from the nerve feed.

    Returns {"changed": bool, ...}. Silent (no nerve event) when nothing
    new was mapped.
    """
    emit = emit or _default_emit
    state_dir = _state_dir()
    feed_path = feed_path or os.path.join(state_dir, "nerve_feed.jsonl")
    cursor_path = cursor_path or os.path.join(state_dir, "wyrd_bridge_cursor.json")
    mirror_path = mirror_path or os.path.join(state_dir, "wyrd_mirror.json")

    VerdandiBridge = _load_wyrdforge()

    entries = [e for e in _read_jsonl(feed_path)
               if isinstance(e.get("_seq"), int)]
    last_seq = _read_cursor(cursor_path)
    new_entries = [e for e in entries if e["_seq"] > last_seq]

    # The cursor always advances past what we have seen — even unmapped
    # events — so the runner never re-scans old noise.
    if entries:
        _write_cursor(cursor_path, max(e["_seq"] for e in entries))

    bridge = VerdandiBridge()
    applied = []
    for entry in entries:
        desc = bridge.apply_event(entry.get("type", ""),
                                  entry.get("data", {}),
                                  entry.get("_ts"))
        if desc and entry["_seq"] > last_seq:
            applied.append(desc)

    if not applied:
        return {"changed": False, "last_seq": last_seq}

    summary = bridge.summary()

    # Durable plain-data projection for Slice 2's inbound bridge.
    try:
        os.makedirs(os.path.dirname(mirror_path), exist_ok=True)
        with open(mirror_path, "w", encoding="utf-8") as fh:
            json.dump({"synced_at": time.time(), **summary},
                      fh, ensure_ascii=False, indent=2)
    except OSError:
        pass

    # The world is live now: manifest/active in the registry. (Slice 0
    # bootstrapped it potential/pending — this is the correction.)
    try:
        import worlds
        worlds.WorldRegistry(path=registry_path).register(
            bridge.world.registry_entry())
    except Exception:
        pass

    emit("wyrd_mirror_synced", {
        "world_id": bridge.world.world_id,
        "reality": bridge.world.identity.reality,
        "new_events": len(applied),
        "entities": summary["entities"],
        "anchors": len(summary["anchors"]),
        "beliefs": len(summary["beliefs"]),
        "applied": applied[:10],
    })
    return {"changed": True, "applied": applied, "summary": summary}


def main() -> int:
    try:
        result = run()
    except Exception as exc:  # never break the nerve; report and exit nonzero
        print(f"wyrd_bridge failed: {exc}")
        return 1
    if result.get("changed"):
        print(f"wyrd_mirror_synced: "
              f"{result['summary']['entities']} entities, "
              f"{len(result['summary']['anchors'])} anchors, "
              f"{len(result['summary']['beliefs'])} beliefs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
