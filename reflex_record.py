#!/usr/bin/env python3
"""Verdandi firing record and audit (VD-T4).

Every firing - and every judged no-fire above a salience floor - is
written to an append-only record with the event digest, the verdict
basis, the action taken and its result. Awareness (and the owner) can
review what the reflexes did and why. The record is JSON Lines on disk:
append-only (never truncated or rewritten), fsynced per entry, and it
survives restart - a new FiringRecord on the same path reads the prior
entries and continues the sequence.
"""
import hashlib
import json
import time
from pathlib import Path

DEFAULT_SALIENCE_FLOOR = 0.5
_SALIENCE_FIELDS = ("salience", "threat", "noise")


def event_digest(event):
    canonical = json.dumps(event, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def event_salience(event):
    vals = []
    for f in _SALIENCE_FIELDS:
        v = event.get(f)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            vals.append(float(v))
    return max(vals) if vals else 0.0


class FiringRecord:
    """Append-only JSONL audit record for reflex firings and no-fires."""

    def __init__(self, path, salience_floor=DEFAULT_SALIENCE_FLOOR):
        self.path = Path(path)
        self.salience_floor = float(salience_floor)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seq = len(self.entries())

    def _append(self, entry):
        self._seq += 1
        entry = {"seq": self._seq, "ts": time.time(), **entry}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True, default=str) + "\n")
            fh.flush()
            import os
            os.fsync(fh.fileno())
        return entry

    def record_firing(self, firing):
        d = firing.to_dict() if hasattr(firing, "to_dict") else dict(firing)
        return self._append({
            "kind": "firing",
            "reflex": d.get("reflex"),
            "action": d.get("action"),
            "event": d.get("event"),
            "event_digest": event_digest(d.get("event") or {}),
            "basis": d.get("basis"),
            "judge": d.get("judge"),
            "fire": True,
            "result": d.get("effect"),
            "latency_ms": d.get("latency_ms"),
        })

    def record_no_fire(self, verdict, event):
        """Record a judged no-fire only at/above the salience floor."""
        if event_salience(event) < self.salience_floor:
            return None
        v = verdict.to_dict() if hasattr(verdict, "to_dict") else dict(verdict)
        return self._append({
            "kind": "no_fire",
            "reflex": v.get("reflex"),
            "action": None,
            "event": dict(event),
            "event_digest": event_digest(event),
            "basis": v.get("basis"),
            "judge": v.get("judge"),
            "fire": False,
            "result": None,
            "latency_ms": None,
        })

    def entries(self):
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def firings(self):
        return [e for e in self.entries() if e.get("kind") == "firing"]

    def for_reflex(self, name):
        return [e for e in self.entries() if e.get("reflex") == name]

    def review(self):
        """Owner/awareness review: counts by kind and by reflex."""
        ents = self.entries()
        by_reflex = {}
        for e in ents:
            by_reflex[e.get("reflex")] = by_reflex.get(e.get("reflex"), 0) + 1
        return {"total": len(ents),
                "firings": sum(1 for e in ents if e.get("kind") == "firing"),
                "no_fires": sum(1 for e in ents if e.get("kind") == "no_fire"),
                "by_reflex": by_reflex}
