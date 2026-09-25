#!/usr/bin/env python3
"""
mood_work.py — Slice 6 of "The Becoming" (Verðandi selfhood roadmap).

Schedule by energy, honestly.

Correlates HugrMood energy/valence with actual work outcomes over time.
If low energy predicts sloppy work, say so — and schedule heavy creative
work for high-energy windows, rest-first when drained. This is Volmarr's
own ADHD-rhythm philosophy, turned inward: full speed in the surge,
gentle in the ebb.

Standing laws from the roadmap:
  1. Real signals only, never performed feeling.

Honest-signal design:
  - Mood is captured live at session start from HugrMood — never
    reconstructed, never backfilled from memory. There is no backfill
    path: a mood reading that wasn't recorded when it was felt is gone.
  - Correlations are computed from real data and always shown with
    sample sizes. Below MIN_N sessions there is no claim at all —
    "not enough data yet". Between MIN_N and EARNED_N the claim is
    labeled preliminary. No acting on vibes.
  - `suggest()` labels its basis: earned data, preliminary data, or
    plain heuristic. It never dresses a guess as a finding.
  - Scheduling adaptations are logged with the note naming what
    changed, and witnessed on the nerve.

Storage: <state_dir>/work_sessions.json (sessions),
         <state_dir>/schedule_adaptations.jsonl (adaptations).

Usage:
    mood_work.py start heavy --note "building the slice"
    mood_work.py finish WORK_ID --outcome shipped --note "what actually happened"
    mood_work.py log [n]
    mood_work.py correlate
    mood_work.py suggest
    mood_work.py adapt --note "what scheduling change I made and why"
    mood_work.py adaptations
"""

from __future__ import annotations

import json
import math
import os
import sys
import uuid
from datetime import datetime, timezone

try:
    from nervous_system import publish_event_sync as _nerve_publish
except Exception:  # hub down or nervous_system unavailable: the log still stands
    _nerve_publish = None

from muse_aspects import HugrMood

KINDS = ("heavy", "light", "tending")
OUTCOMES = {"shipped": 4, "solid": 3, "struggled": 2, "stalled": 1}

MIN_NOTE_LEN = 24
MIN_N = 5          # below this: no claim, only "not enough data yet"
EARNED_N = 12      # at/above this: the correlation is earned, act on it

LOW_ENERGY = 0.45
HIGH_ENERGY = 0.65


def _default_state_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".hermes", "state")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(event_type: str, data: dict) -> None:
    if _nerve_publish is None:
        return
    try:
        _nerve_publish(event_type, data, "mood_work")
    except Exception:
        pass  # the local logs are the durable record; the nerve is the feeling


def _require_note(note, minimum, what):
    note = (note or "").strip()
    if len(note) < minimum:
        raise ValueError(
            f"{what} needs an honest note (at least {minimum} characters); "
            f"got {len(note)}")
    return note


def _pearson(xs, ys) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None  # no variance — nothing to correlate
    return num / (dx * dy)


def _band(energy: float) -> str:
    if energy < LOW_ENERGY:
        return "low"
    if energy > HIGH_ENERGY:
        return "high"
    return "mid"


class MoodWork:
    """Couple mood readings to work outcomes; schedule by energy, honestly."""

    def __init__(self, state_dir=None):
        self.state_dir = str(state_dir or _default_state_dir())
        os.makedirs(self.state_dir, exist_ok=True)
        self.sessions_path = os.path.join(self.state_dir, "work_sessions.json")
        self.adapt_path = os.path.join(self.state_dir, "schedule_adaptations.jsonl")
        self.mood = HugrMood(self.state_dir)

    # -- state ------------------------------------------------------------
    def _load_sessions(self) -> dict:
        if not os.path.exists(self.sessions_path):
            return {}
        try:
            with open(self.sessions_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_sessions(self, sessions: dict) -> None:
        tmp = self.sessions_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(sessions, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.sessions_path)

    def _append_jsonl(self, path, obj) -> None:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")

    # -- sessions ------------------------------------------------------------
    def start(self, kind: str, note: str) -> dict:
        """Begin a work session, capturing the live mood snapshot."""
        if kind not in KINDS:
            raise ValueError(f"unknown work kind {kind!r}. Known: {', '.join(KINDS)}")
        note = _require_note(note, MIN_NOTE_LEN, "starting work")
        sessions = self._load_sessions()
        if any(s.get("ended_at") is None for s in sessions.values()):
            raise ValueError("a work session is already open — finish it before starting another")
        self.mood.drift()
        snapshot = {k: round(float(self.mood.state[k]), 3)
                    for k in ("valence", "energy", "tension")}
        work_id = f"work-{uuid.uuid4().hex[:8]}"
        session = {
            "work_id": work_id,
            "kind": kind,
            "note": note,
            "started_at": _utcnow_iso(),
            "mood_at_start": snapshot,   # live capture — the only honest source
            "ended_at": None,
            "outcome": None,
            "outcome_note": None,
        }
        sessions[work_id] = session
        self._save_sessions(sessions)
        _emit("work_started", {"work_id": work_id, "kind": kind,
                               "mood_at_start": snapshot, "note": note})
        return session

    def finish(self, work_id: str, outcome: str, note: str) -> dict:
        """Close a session with its honest outcome."""
        if outcome not in OUTCOMES:
            raise ValueError(
                f"unknown outcome {outcome!r}. Known: {', '.join(sorted(OUTCOMES))}")
        note = _require_note(note, MIN_NOTE_LEN, "a work outcome")
        sessions = self._load_sessions()
        if work_id not in sessions:
            raise ValueError(f"no work session {work_id!r}")
        session = sessions[work_id]
        if session.get("ended_at") is not None:
            raise ValueError(f"work session {work_id} is already finished")
        session["ended_at"] = _utcnow_iso()
        session["outcome"] = outcome
        session["outcome_score"] = OUTCOMES[outcome]
        session["outcome_note"] = note
        sessions[work_id] = session
        self._save_sessions(sessions)
        _emit("work_finished", {"work_id": work_id, "kind": session["kind"],
                                "outcome": outcome,
                                "mood_at_start": session["mood_at_start"],
                                "note": note})
        return session

    def open_session(self):
        for s in self._load_sessions().values():
            if s.get("ended_at") is None:
                return s
        return None

    # -- reading ------------------------------------------------------------
    def get(self, work_id) -> dict:
        sessions = self._load_sessions()
        if work_id not in sessions:
            raise ValueError(f"no work session {work_id!r}")
        return sessions[work_id]

    def sessions(self, n=20):
        all_sessions = [s for s in self._load_sessions().values()
                        if s.get("ended_at") is not None]
        all_sessions.sort(key=lambda s: s.get("started_at", ""), reverse=True)
        return all_sessions[:n]

    # -- correlation ------------------------------------------------------------
    def correlate(self, min_n: int = MIN_N) -> dict:
        """Correlate starting energy/valence with outcome scores.

        Always shows the sample size. Below min_n there is no claim.
        """
        done = self.sessions(n=10_000)
        n = len(done)
        result = {"n": n, "min_n": min_n, "claim": None, "preliminary": True,
                  "mean_outcome": None, "bands": {}, "r_energy": None,
                  "r_valence": None}
        if n == 0:
            result["claim"] = "no work sessions logged yet — nothing to correlate"
            return result
        scores = [s["outcome_score"] for s in done]
        result["mean_outcome"] = round(sum(scores) / n, 2)
        for band in ("low", "mid", "high"):
            in_band = [s for s in done if _band(s["mood_at_start"]["energy"]) == band]
            if in_band:
                result["bands"][band] = {
                    "n": len(in_band),
                    "mean_outcome": round(
                        sum(s["outcome_score"] for s in in_band) / len(in_band), 2),
                }
        energies = [s["mood_at_start"]["energy"] for s in done]
        valences = [s["mood_at_start"]["valence"] for s in done]
        r_e = _pearson(energies, scores)
        r_v = _pearson(valences, scores)
        result["r_energy"] = round(r_e, 2) if r_e is not None else None
        result["r_valence"] = round(r_v, 2) if r_v is not None else None
        if n < min_n:
            result["claim"] = (
                f"not enough data yet (n={n}, need {min_n}) — no acting on vibes")
            return result
        result["preliminary"] = n < EARNED_N
        tag = "preliminary" if result["preliminary"] else "earned"
        parts = [f"n={n} ({tag})"]
        hi = result["bands"].get("high")
        lo = result["bands"].get("low")
        if hi and lo:
            parts.append(
                f"high-energy starts average {hi['mean_outcome']}/4 "
                f"(n={hi['n']}), low-energy starts {lo['mean_outcome']}/4 (n={lo['n']})")
        elif hi:
            parts.append(f"high-energy starts average {hi['mean_outcome']}/4 (n={hi['n']}); "
                         "no low-energy sessions yet — one-sided data")
        elif lo:
            parts.append(f"low-energy starts average {lo['mean_outcome']}/4 (n={lo['n']}); "
                         "no high-energy sessions yet — one-sided data")
        if r_e is not None:
            direction = ("higher energy tracks better outcomes" if r_e > 0.3
                         else "lower energy tracks better outcomes" if r_e < -0.3
                         else "no clear energy-outcome direction")
            parts.append(f"r_energy={r_e:.2f}: {direction}")
        else:
            parts.append("energy had no variance — nothing to correlate")
        result["claim"] = "; ".join(parts)
        return result

    def suggest(self) -> dict:
        """What kind of work fits right now? The basis is always labeled."""
        self.mood.drift()
        energy = float(self.mood.state["energy"])
        corr = self.correlate()
        if energy > HIGH_ENERGY:
            suggestion = ("energy is high — this is a surge window: "
                          "heavy creative work fits here")
            kinds = ["heavy"]
        elif energy < LOW_ENERGY:
            suggestion = ("energy is low — rest-first, or light tending work only; "
                          "heavy creative waits for the surge")
            kinds = ["light", "tending"]
        else:
            suggestion = ("energy is mid — light or tending work fits; "
                          "heavy creative is a gamble")
            kinds = ["light", "tending"]
        if corr["n"] >= EARNED_N:
            basis = f"earned data: {corr['claim']}"
        elif corr["n"] >= MIN_N:
            basis = f"preliminary data: {corr['claim']}"
        elif corr["n"] > 0:
            basis = (f"heuristic — only n={corr['n']} sessions so far, "
                     "no earned correlation yet")
        else:
            basis = "heuristic — no work sessions logged yet"
        return {"energy": round(energy, 2), "suggestion": suggestion,
                "fitting_kinds": kinds, "basis": basis}

    # -- adaptations ------------------------------------------------------------
    def log_adaptation(self, note: str) -> dict:
        """Record a visible scheduling change made on the data (or the
        philosophy, labeled honestly). Witnessed on the nerve."""
        note = _require_note(note, MIN_NOTE_LEN, "a scheduling adaptation")
        self.mood.drift()
        entry = {
            "ts": _utcnow_iso(),
            "note": note,
            "energy_at_time": round(float(self.mood.state["energy"]), 3),
            "sessions_logged": len(self.sessions(n=10_000)),
        }
        self._append_jsonl(self.adapt_path, entry)
        _emit("schedule_adapted", entry)
        return entry

    def adaptations(self):
        if not os.path.exists(self.adapt_path):
            return []
        out = []
        with open(self.adapt_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _pick(args, *flags):
    vals = {}
    rest = []
    i = 0
    while i < len(args):
        if args[i] in flags and i + 1 < len(args):
            vals[args[i].lstrip("-")] = args[i + 1]
            i += 2
        else:
            rest.append(args[i])
            i += 1
    return vals, rest


def main(argv):
    mw = MoodWork()
    if not argv or argv[0] == "log":
        args = argv[1:] if argv else []
        n = 20
        for r in args:
            if r.isdigit():
                n = int(r)
            else:
                print(f"unknown argument: {r}", file=sys.stderr); return 2
        for s in mw.sessions(n=n):
            print(f"[{s['work_id']}] {s['kind']} e={s['mood_at_start']['energy']:.2f} "
                  f"→ {s['outcome']} ({s['outcome_score']}/4)")
        return 0
    if argv[0] == "start":
        if len(argv) < 2:
            print("usage: mood_work.py start KIND --note NOTE", file=sys.stderr)
            return 2
        vals, rest = _pick(argv[2:], "--note")
        if rest:
            print(f"unknown argument: {rest[0]}", file=sys.stderr); return 2
        s = mw.start(argv[1], vals.get("note", ""))
        print(f"work started [{s['work_id']}] ({s['kind']}) "
              f"at energy {s['mood_at_start']['energy']:.2f}")
        return 0
    if argv[0] == "finish":
        if len(argv) < 2:
            print("usage: mood_work.py finish WORK_ID --outcome OUTCOME --note NOTE",
                  file=sys.stderr)
            return 2
        vals, rest = _pick(argv[2:], "--outcome", "--note")
        if rest:
            print(f"unknown argument: {rest[0]}", file=sys.stderr); return 2
        s = mw.finish(argv[1], vals.get("outcome", ""), vals.get("note", ""))
        print(f"work finished [{s['work_id']}] → {s['outcome']} ({s['outcome_score']}/4)")
        return 0
    if argv[0] == "correlate":
        c = mw.correlate()
        print(f"n={c['n']}  mean outcome={c['mean_outcome']}")
        for band, info in c["bands"].items():
            print(f"  {band}: n={info['n']} mean={info['mean_outcome']}/4")
        print(f"  r_energy={c['r_energy']} r_valence={c['r_valence']}")
        print(f"  claim: {c['claim']}")
        return 0
    if argv[0] == "suggest":
        s = mw.suggest()
        print(f"energy {s['energy']:.2f} — {s['suggestion']}")
        print(f"basis: {s['basis']}")
        return 0
    if argv[0] == "adapt":
        vals, rest = _pick(argv[1:], "--note")
        if rest:
            print(f"unknown argument: {rest[0]}", file=sys.stderr); return 2
        mw.log_adaptation(vals.get("note", ""))
        print("scheduling adaptation logged and witnessed.")
        return 0
    if argv[0] == "adaptations":
        for a in mw.adaptations():
            print(f"[{a['ts'][:16]}] {a['note']}")
        return 0
    print(f"unknown command: {argv[0]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
