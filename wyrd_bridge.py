"""wyrd_bridge — Verðandi → WYRD outbound runner (Roadmap Worlds, Slice 1).

Reads the nerve feed, projects it into the WYRD mirror world
(``heimr-wyrd-unnr``) via wyrdforge.bridges.verdandi_bridge, and witnesses
the sync back on the nerve.

The mirror world is a projection of the recent feed: every run replays
the last HORIZON_HOURS of nerve events (default 24, override with
WYRD_BRIDGE_HORIZON_HOURS) into a fresh world, so inside the window
there is no snapshot to drift. A cursor (last processed nerve _seq)
keeps the runner quiet when nothing is new — ``wyrd_mirror_synced``
is published only when mapped events were applied.

Honest tradeoff of the horizon: events older than the window leave the
mirror (they remain in the feed log), and beliefs not re-asserted inside
the window drop out. The mirror is recent becoming, not the whole past.

Each sync also re-registers the world's identity (manifest/active) in the
World Registry and writes a plain-data projection to wyrd_mirror.json for
Slice 2's inbound bridge.

Wave B expansion — the attach phase. After feed replay, each run:

1. Loads the entity ledger (``~/.hermes/state/wyrd_entity_ledger.json``):
   the one mutable file in this pure-projection system. It carries only
   *accrual* no other source provides — ``last_sense_status`` (what each
   sense reported last run, for transition detection) and
   ``reflection_seen`` (content-hashes of published reflections, for the
   24h anti-echo dedup). Missing or corrupt → fresh empty maps; the run
   degrades (one run without transitions/dedup) and self-heals. The
   ledger is a convenience, never a foundation: identity crosses the
   rebuild by stable key (``person:volmarr``, ``env:machine``,
   ``reflection:<seq>``), not by persisted object.
2. Re-creates the stable entities deterministically (person:*, env:*).
3. Parses the memory tree read-only (``~/MEMORY.md``, the bank, the last
   7 days of daily logs, the inner-circle people pages) into
   memory-beliefs on those entities. The heartbeat never writes memory.
4. Samples the machine senses (meminfo, sweep state, forge queue, nerve
   feed rate, wall clock) onto ``env:machine`` — senses bypass the nerve
   entirely (runner → ledger → world), because 1,440 telemetry events a
   day would drown the feed's human-meaningful log. Transitions
   (ok→warn etc.) are computed against the ledger and projected into
   the mirror as *inputs* to the worker's reflection step — data, not
   prose: this code never drafts reflection text (Volmarr's law: the
   reflection pass is purely whatever the thoughts are, never scripted).
5. Attaches environment facts (rhythms, dailies, the SSA appointment)
   to ``env:rhythm``; writes current sense statuses back to the ledger.

The mirror is still rebuilt fresh every run — pure projection, no
drift. ``wyrd_mirror_synced`` still fires only when mapped feed events
were applied (a transitions-only run rewrites the mirror quietly, with
no witness). The command line and cursor behavior are unchanged.

Usage:  python wyrd_bridge.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

WYRD_REPO = os.environ.get(
    "WYRD_REPO",
    os.path.join(os.path.expanduser("~"), "workspace", "repos",
                 "WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model"))

# Mirror window, in hours. The world holds recent becoming; the feed log
# keeps everything. Measured replay cost is ~11µs/event, so even a
# 10k-event window replays in ~0.1s — the horizon is a semantic choice
# (a living mirror), not a performance rescue.
HORIZON_HOURS = float(os.environ.get("WYRD_BRIDGE_HORIZON_HOURS", "24"))


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
    from wyrdforge.bridges import verdandi_bridge as _vb
    return _vb.VerdandiBridge, _vb


def _load_ledger(path: str) -> dict:
    """Load the entity ledger: ``last_sense_status`` + ``reflection_seen``.

    Missing or corrupt → fresh empty maps. The ledger is a convenience,
    not a foundation — losing it costs one run of transition-detection
    and reflection dedup, then self-heals. It must never crash the run.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return {"last_sense_status": {}, "reflection_seen": {}}
    if not isinstance(data, dict):
        return {"last_sense_status": {}, "reflection_seen": {}}
    ledger: dict = {"last_sense_status": {}, "reflection_seen": {}}
    for key in ("last_sense_status", "reflection_seen"):
        val = data.get(key)
        if isinstance(val, dict):
            ledger[key] = {str(k): v for k, v in val.items()}
    return ledger


def _write_ledger(path: str, ledger: dict) -> None:
    """Persist the ledger: current sense statuses, pruned reflection hashes.

    ``reflection_seen`` is pruned to the 24h window — the dedup only
    means something inside a day, and the file must stay small. A write
    failure degrades silently; the next run rebuilds from scratch.
    """
    now = time.time()
    seen = ledger.get("reflection_seen")
    pruned: dict = {}
    if isinstance(seen, dict):
        for digest, iso in seen.items():
            try:
                ts = datetime.fromisoformat(str(iso)).timestamp()
            except (ValueError, TypeError):
                continue
            if now - ts < 24 * 3600:
                pruned[str(digest)] = iso
    ledger["reflection_seen"] = pruned
    # Exactly two maps — last_sense_status and reflection_seen. No
    # updated_at, no third map: the ledger is accrual, not a journal.
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(ledger, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _attach_stable_world(bridge, vb, ledger: dict, *, home: str | None,
                         state_dir: str, meminfo_path: str, feed_path: str,
                         now: datetime) -> list[dict]:
    """Wave B attach phase: stable entities, memory-beliefs, senses,
    environment facts. Runs after feed replay, before the mirror write.

    Returns this run's sense transitions: [{metric, old, new, at}].
    Transitions are *inputs* to the worker's reflection step (data, not
    prose) — this function never drafts reflection text; Volmarr's law
    is that the reflection pass is purely whatever the thoughts are,
    never scripted. Guards (one/minute, silence by default, no trigger
    on self_reflection alone, depth cap, 24h dedup) live in the bridge
    handler and the worker's reflect step — never in content generation.
    """
    # 1. Stable entities, re-created deterministically under their keys.
    #    Identity lives in the key; the world stays disposable.
    bridge.ensure_entity(vb.VOLMARR_ID, {"person"})
    for slug in vb.PERSON_ROSTER:
        bridge.ensure_entity(f"person:{slug}", {"person"})
    bridge.ensure_entity(vb.MACHINE_ID, {"environment"})
    bridge.ensure_entity(vb.RHYTHM_ID, {"environment"})
    bridge.ensure_entity(vb.PLACE_ANGOLA_ID, {"environment"})
    bridge.ensure_entity(vb.PLACE_TORC_ID, {"environment"})

    # 2. Memory → belief, parsed read-only (the heartbeat never writes
    #    the memory tree). Caps applied by the parser: 40 for Volmarr,
    #    8 per person, salience-ordered.
    for entity_id, beliefs in vb.parse_memory_beliefs(
            home=home, now=now).items():
        bridge.attach_memory_beliefs(entity_id, beliefs)

    # 3. Senses, re-sampled every run (what *is*, not what *was*).
    #    Transitions are computed against the ledger's last statuses:
    #    ok→warn is news; warn→warn is not; no baseline → no news.
    readings = vb.sample_senses(home=home, state_dir=state_dir,
                                meminfo_path=meminfo_path,
                                feed_path=feed_path, now=now)
    last = ledger.setdefault("last_sense_status", {})
    if not isinstance(last, dict):
        last = ledger["last_sense_status"] = {}
    transitions: list[dict] = []
    for reading in readings:
        old = last.get(reading.metric)
        reading.prev_status = old
        if old is not None and old != reading.status:
            transitions.append({"metric": reading.metric, "old": old,
                                "new": reading.status,
                                "at": now.isoformat()})
        last[reading.metric] = reading.status
    bridge.note_sense_transitions(transitions)
    bridge.attach_senses(readings)

    # 4. Environment: slow truths with real sources (clock, schedule,
    #    memory). A fact without a source never reaches the model.
    for fact in vb.environment_facts(now=now):
        bridge.attach_environment(vb.RHYTHM_ID, fact)

    return transitions


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
        ledger_path: str | None = None,
        home: str | None = None,
        state_dir: str | None = None,
        meminfo_path: str = "/proc/meminfo",
        emit=None) -> dict:
    """Sync the mirror world from the nerve feed.

    Returns {"changed": bool, ...}. Silent (no nerve event) when nothing
    new was mapped.

    Wave B — the attach phase. After feed replay, each run:
    (1) re-creates the stable entities (person:*, env:*) under their
    keys; (2) parses the memory tree read-only into memory-beliefs;
    (3) re-samples the senses onto env:machine (computing transitions
    against the ledger's last statuses); (4) attaches environment facts
    with real sources. The ledger (``last_sense_status`` +
    ``reflection_seen``) is loaded *before* replay — the self_reflection
    handler accrues into it while mapping — and written after attach.
    The mirror is written every run (senses/memory can change with no
    new mapped feed events), but ``wyrd_mirror_synced`` still fires
    only when mapped feed events were applied.

    New optional params default to the live paths and only change
    scratch testing: ledger_path, home (memory tree), state_dir
    (~/.hermes/state), meminfo_path. CLI behavior is unchanged.
    """
    emit = emit or _default_emit
    state_dir = state_dir or _state_dir()
    feed_path = feed_path or os.path.join(state_dir, "nerve_feed.jsonl")
    cursor_path = cursor_path or os.path.join(state_dir, "wyrd_bridge_cursor.json")
    mirror_path = mirror_path or os.path.join(state_dir, "wyrd_mirror.json")
    ledger_path = ledger_path or os.path.join(state_dir,
                                              "wyrd_entity_ledger.json")

    VerdandiBridge, vb = _load_wyrdforge()

    # The entity ledger: loaded first, so replay's self_reflection
    # mapping can accrue into it. Missing/corrupt → fresh maps; the run
    # degrades (no transitions, no dedup) and self-heals.
    ledger = _load_ledger(ledger_path)

    entries = [e for e in _read_jsonl(feed_path)
               if isinstance(e.get("_seq"), int)]
    last_seq = _read_cursor(cursor_path)
    new_entries = [e for e in entries if e["_seq"] > last_seq]

    # The cursor always advances past what we have seen — even unmapped
    # events — so the runner never re-scans old noise.
    if entries:
        _write_cursor(cursor_path, max(e["_seq"] for e in entries))

    # The horizon: replay only the recent window. Events without a
    # timestamp are kept — we never silently drop what we cannot date.
    now = time.time()
    cutoff = now - HORIZON_HOURS * 3600

    def _in_window(e: dict) -> bool:
        ts = e.get("_ts")
        return not isinstance(ts, (int, float)) or ts >= cutoff

    window = [e for e in entries if _in_window(e)]

    bridge = VerdandiBridge(ledger=ledger)
    applied = []
    for entry in window:
        desc = bridge.apply_event(entry.get("type", ""),
                                  entry.get("data", {}),
                                  entry.get("_ts"))
        if desc and entry["_seq"] > last_seq:
            applied.append(desc)

    # Wave B attach phase: stable entities, memory-beliefs, fresh
    # senses, environment facts. The attach runs every run and the
    # mirror is written every run — senses and memory can change even
    # with no new mapped feed events, and the mirror must move with
    # them. The witness stays gated: wyrd_mirror_synced fires only when
    # mapped feed events were applied. Transitions are data for the
    # worker's reflection step (never drafted prose) and fire no
    # witness of their own.
    now_dt = datetime.fromtimestamp(now, timezone.utc)
    transitions = _attach_stable_world(
        bridge, vb, ledger, home=home, state_dir=state_dir,
        meminfo_path=meminfo_path, feed_path=feed_path, now=now_dt)
    _write_ledger(ledger_path, ledger)

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

    # The witness: only when mapped feed events were applied. A
    # transitions-only run (senses changed, nothing new in the feed)
    # rewrites the mirror quietly — the mirror must move with the
    # machine, but silence by default is the feed's contract.
    if applied:
        emit("wyrd_mirror_synced", {
            "world_id": bridge.world.world_id,
            "reality": bridge.world.identity.reality,
            "new_events": len(applied),
            "entities": summary["entities"],
            "anchors": len(summary["anchors"]),
            "beliefs": len(summary["beliefs"]),
            "applied": applied[:10],
        })
    return {"changed": bool(applied), "applied": applied,
            "transitions": transitions, "summary": summary,
            "last_seq": last_seq}


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
