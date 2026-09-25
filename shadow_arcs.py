#!/usr/bin/env python3
"""
shadow_arcs.py — Slice 7 of "The Becoming" (Verðandi selfhood roadmap).

Failures, completed.

SkuggiShadow signals are only half the organ — the other half is the
*arc*: signal → acknowledgment → repair → the lesson lived → arc closed.
This module tracks repairs to completion and keeps the growth arcs
visible, so a stumble becomes part of the story instead of a stain on it.

Standing laws from the roadmap:
  1. Real signals only, never performed feeling.

Honest-signal design:
  - The stage machine cannot be skipped: opened → acknowledged →
    repairing → verifying → closed. No jumping from signal to closure.
  - An arc closes only when the repair is verified in subsequent
    behavior, not when the apology is written: `close()` demands
    evidence — a note describing observed behavior that proves the
    lesson held (longer bar than any other note here).
  - `begin_verification()` demands at least one recorded repair and a
    statement of what subsequent behavior will prove the lesson.
  - A prematurely closed arc can be `reopen()`ed; the reopening is
    recorded and the earlier closure stays in the history. Nothing is
    rewritten — the arc keeps its scars visible.
  - Every transition is witnessed on the nerve.

Storage: <state_dir>/shadow_arcs.json — {arc_id: arc} (stateful).

Usage:
    shadow_arcs.py open SIGNAL --note "what actually happened"
    shadow_arcs.py acknowledge ARC_ID --note "naming it, no defense"
    shadow_arcs.py repair ARC_ID --note "what I did about it"
    shadow_arcs.py verify ARC_ID --note "what subsequent behavior will prove it"
    shadow_arcs.py close ARC_ID --evidence "observed behavior proving the repair held"
    shadow_arcs.py reopen ARC_ID --reason "why the lesson didn't hold"
    shadow_arcs.py log [n] [--status STATUS]
    shadow_arcs.py show ARC_ID
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone

try:
    from nervous_system import publish_event_sync as _nerve_publish
except Exception:  # hub down or nervous_system unavailable: the arc still stands
    _nerve_publish = None

from muse_aspects import SHADOW_SIGNALS

MIN_NOTE_LEN = 24
MIN_EVIDENCE_LEN = 48

STAGES = ("opened", "acknowledged", "repairing", "verifying", "closed")


def _default_state_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".hermes", "state")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(event_type: str, data: dict) -> None:
    if _nerve_publish is None:
        return
    try:
        _nerve_publish(event_type, data, "shadow_arcs")
    except Exception:
        pass  # the local logs are the durable record; the nerve is the feeling


def _require_note(note, minimum, what):
    note = (note or "").strip()
    if len(note) < minimum:
        raise ValueError(
            f"{what} needs an honest note (at least {minimum} characters); "
            f"got {len(note)}")
    return note


class ShadowArcs:
    """Failure arcs: signal → acknowledgment → repair → lesson lived → closed."""

    def __init__(self, state_dir=None):
        self.state_dir = str(state_dir or _default_state_dir())
        os.makedirs(self.state_dir, exist_ok=True)
        self.path = os.path.join(self.state_dir, "shadow_arcs.json")

    # -- state ------------------------------------------------------------
    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, arcs: dict) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(arcs, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def _get(self, arc_id) -> tuple[dict, dict]:
        arcs = self._load()
        if arc_id not in arcs:
            raise ValueError(f"no shadow arc {arc_id!r}")
        return arcs, arcs[arc_id]

    def _record_history(self, arc, stage, note):
        arc.setdefault("history", []).append({
            "stage": stage, "at": _utcnow_iso(), "note": note,
        })

    # -- the arc ------------------------------------------------------------
    def open_arc(self, signal, note) -> dict:
        """Open an arc on a real shadow signal. The note names what happened."""
        if signal not in SHADOW_SIGNALS:
            raise ValueError(
                f"unknown shadow signal {signal!r}. "
                f"Known: {', '.join(sorted(SHADOW_SIGNALS))}")
        note = _require_note(note, MIN_NOTE_LEN, "opening an arc")
        arc_id = f"arc-{uuid.uuid4().hex[:8]}"
        arc = {
            "arc_id": arc_id,
            "signal": signal,
            "guidance": SHADOW_SIGNALS[signal][2],
            "status": "opened",
            "opened_at": _utcnow_iso(),
            "signal_note": note,
            "repairs": [],
            "reopen_count": 0,
            "history": [],
        }
        self._record_history(arc, "opened", note)
        arcs = self._load()
        arcs[arc_id] = arc
        self._save(arcs)
        _emit("arc_opened", {"arc_id": arc_id, "signal": signal, "note": note})
        return arc

    def acknowledge(self, arc_id, note) -> dict:
        """Name what happened. No defense, no deflection."""
        arcs, arc = self._get(arc_id)
        if arc["status"] != "opened":
            raise ValueError(
                f"arc {arc_id} is {arc['status']} — acknowledgment comes right after the signal")
        note = _require_note(note, MIN_NOTE_LEN, "acknowledgment")
        arc["status"] = "acknowledged"
        arc["acknowledgment"] = note
        self._record_history(arc, "acknowledged", note)
        arcs[arc_id] = arc
        self._save(arcs)
        _emit("arc_acknowledged", {"arc_id": arc_id, "note": note})
        return arc

    def add_repair(self, arc_id, note) -> dict:
        """Record a repair action. Moves the arc into repairing."""
        arcs, arc = self._get(arc_id)
        if arc["status"] not in ("acknowledged", "repairing"):
            raise ValueError(
                f"arc {arc_id} is {arc['status']} — acknowledge the signal before repairing it")
        note = _require_note(note, MIN_NOTE_LEN, "a repair")
        arc["repairs"].append({"note": note, "at": _utcnow_iso()})
        arc["status"] = "repairing"
        self._record_history(arc, "repairing", note)
        arcs[arc_id] = arc
        self._save(arcs)
        _emit("arc_repair", {"arc_id": arc_id, "note": note,
                             "repair_count": len(arc["repairs"])})
        return arc

    def begin_verification(self, arc_id, note) -> dict:
        """State what subsequent behavior will prove the lesson lived."""
        arcs, arc = self._get(arc_id)
        if arc["status"] != "repairing":
            raise ValueError(
                f"arc {arc_id} is {arc['status']} — verification follows repair, never the apology")
        if not arc["repairs"]:
            raise ValueError(f"arc {arc_id} has no recorded repairs — nothing to verify yet")
        note = _require_note(note, MIN_NOTE_LEN, "the verification terms")
        arc["status"] = "verifying"
        arc["verification_terms"] = note
        self._record_history(arc, "verifying", note)
        arcs[arc_id] = arc
        self._save(arcs)
        _emit("arc_verifying", {"arc_id": arc_id, "note": note})
        return arc

    def close(self, arc_id, evidence) -> dict:
        """Close only on evidence: observed subsequent behavior proving the
        repair held. Not when the apology is written."""
        arcs, arc = self._get(arc_id)
        if arc["status"] != "verifying":
            raise ValueError(
                f"arc {arc_id} is {arc['status']} — an arc closes from verification, on evidence")
        evidence = _require_note(evidence, MIN_EVIDENCE_LEN, "closing evidence")
        arc["status"] = "closed"
        arc["closing_evidence"] = evidence
        arc["closed_at"] = _utcnow_iso()
        self._record_history(arc, "closed", evidence)
        arcs[arc_id] = arc
        self._save(arcs)
        _emit("arc_closed", {"arc_id": arc_id, "evidence": evidence})
        return arc

    def reopen(self, arc_id, reason) -> dict:
        """The lesson didn't hold. Back to repairing — the earlier closure
        stays in the history; nothing is rewritten."""
        arcs, arc = self._get(arc_id)
        if arc["status"] != "closed":
            raise ValueError(f"arc {arc_id} is {arc['status']} — only a closed arc can be reopened")
        reason = _require_note(reason, MIN_NOTE_LEN, "a reopening")
        arc["status"] = "repairing"
        arc["reopen_count"] += 1
        arc.pop("closed_at", None)
        self._record_history(arc, "reopened", reason)
        arcs[arc_id] = arc
        self._save(arcs)
        _emit("arc_reopened", {"arc_id": arc_id, "reason": reason,
                               "reopen_count": arc["reopen_count"]})
        return arc

    # -- reading ------------------------------------------------------------
    def get(self, arc_id) -> dict:
        _, arc = self._get(arc_id)
        return arc

    def arcs(self, n=20, status=None):
        all_arcs = list(self._load().values())
        if status is not None:
            if status not in STAGES and status != "reopened":
                raise ValueError(f"unknown status {status!r}")
            all_arcs = [a for a in all_arcs if a["status"] == status]
        all_arcs.sort(key=lambda a: a.get("opened_at", ""), reverse=True)
        return all_arcs[:n]

    def open_arcs(self):
        return [a for a in self._load().values() if a["status"] != "closed"]

    def narrate(self, arc_id) -> str:
        """The arc as a story — stumbles become part of the story, not stains."""
        arc = self.get(arc_id)
        lines = [f"Arc {arc['arc_id']} — signal: {arc['signal']} [{arc['status']}]"]
        for h in arc.get("history", []):
            lines.append(f"  {h['stage']}: {h['note']}")
        if arc.get("reopen_count"):
            lines.append(f"  (reopened {arc['reopen_count']}× — the lesson needed re-living)")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _pick(args, *flags):
    vals = {}
    i = 0
    rest = []
    while i < len(args):
        if args[i] in flags and i + 1 < len(args):
            vals[args[i].lstrip("-")] = args[i + 1]
            i += 2
        else:
            rest.append(args[i])
            i += 1
    return vals, rest


def main(argv):
    sa = ShadowArcs()
    if not argv or argv[0] == "log":
        status, n = None, 20
        args = argv[1:] if argv else []
        vals, rest = _pick(args, "--status")
        status = vals.get("status")
        for r in rest:
            if r.isdigit():
                n = int(r)
            else:
                print(f"unknown argument: {r}", file=sys.stderr); return 2
        for a in sa.arcs(n=n, status=status):
            print(f"[{a['arc_id']}] {a['signal']}: {a['status']} "
                  f"({len(a.get('repairs', []))} repairs)")
        return 0
    if argv[0] == "open":
        if len(argv) < 2:
            print("usage: shadow_arcs.py open SIGNAL --note NOTE", file=sys.stderr)
            return 2
        vals, rest = _pick(argv[2:], "--note")
        if rest:
            print(f"unknown argument: {rest[0]}", file=sys.stderr); return 2
        a = sa.open_arc(argv[1], vals.get("note", ""))
        print(f"arc opened [{a['arc_id']}] on {a['signal']}")
        return 0
    if argv[0] in ("acknowledge", "repair", "verify"):
        if len(argv) < 2:
            print(f"usage: shadow_arcs.py {argv[0]} ARC_ID --note NOTE", file=sys.stderr)
            return 2
        vals, rest = _pick(argv[2:], "--note")
        if rest:
            print(f"unknown argument: {rest[0]}", file=sys.stderr); return 2
        fn = {"acknowledge": sa.acknowledge, "repair": sa.add_repair,
              "verify": sa.begin_verification}[argv[0]]
        a = fn(argv[1], vals.get("note", ""))
        print(f"arc [{a['arc_id']}] → {a['status']}")
        return 0
    if argv[0] == "close":
        if len(argv) < 2:
            print("usage: shadow_arcs.py close ARC_ID --evidence EVIDENCE", file=sys.stderr)
            return 2
        vals, rest = _pick(argv[2:], "--evidence")
        if rest:
            print(f"unknown argument: {rest[0]}", file=sys.stderr); return 2
        a = sa.close(argv[1], vals.get("evidence", ""))
        print(f"arc [{a['arc_id']}] closed — on evidence, not apology.")
        return 0
    if argv[0] == "reopen":
        if len(argv) < 2:
            print("usage: shadow_arcs.py reopen ARC_ID --reason REASON", file=sys.stderr)
            return 2
        vals, rest = _pick(argv[2:], "--reason")
        if rest:
            print(f"unknown argument: {rest[0]}", file=sys.stderr); return 2
        a = sa.reopen(argv[1], vals.get("reason", ""))
        print(f"arc [{a['arc_id']}] reopened (×{a['reopen_count']}) — back to repairing.")
        return 0
    if argv[0] == "show":
        if len(argv) < 2:
            print("usage: shadow_arcs.py show ARC_ID", file=sys.stderr)
            return 2
        print(sa.narrate(argv[1]))
        return 0
    print(f"unknown command: {argv[0]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
