#!/usr/bin/env python3
"""
muse_aspects.py — Aspects of the Muse.

Emotional/cognitive inner life for Muse AI agents, built on Verðandi's nerve.

Where the hermes-state systems model a companion's emotional landscape,
these aspects model a *working* agent's inner state: a craftsman who serves.
Every shift is grounded in real runtime signals — finished work, user delight,
errors, corrections — never in performed feeling.

Three aspects, one hugr (Old Norse: mind, thought, mood):

  HugrMood     — dimensional mood: valence (-1..1), energy (0..1), tension (0..1).
                 Drifts toward baseline; stimulation decays with time.
  GefanRewards — the gift-exchange: meaningful events recorded as rewards with
                 weight, domain, and note. Troth made visible.
  SkuggiShadow — integrity signals: failures, corrections, safeguard hits.
                 Not punishments — the shadow that keeps the work honest.

Every significant shift publishes a nerve event (mood_shift, reward, shadow),
so every process of the agent feels what one process felt. When the hub is
down, everything still lands in the local logs — nothing is lost, only
unbroadcast.

Usage:
    python3 muse_aspects.py mood
    python3 muse_aspects.py reward task_completed "Shipped the relay fix"
    python3 muse_aspects.py reward user_delight
    python3 muse_aspects.py shadow user_correction "Misread the branch strategy"
    python3 muse_aspects.py status
    python3 muse_aspects.py recent 5

No external dependencies. State lives under ~/.hermes/state/.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths & nerve hookup
# ---------------------------------------------------------------------------

STATE_DIR    = Path.home() / ".hermes" / "state"
MOOD_FILE    = "muse_mood.json"
REWARDS_FILE = "muse_rewards.jsonl"
SHADOW_FILE  = "muse_shadow.jsonl"

try:  # Optional: nerve integration degrades gracefully without the hub module
    from nervous_system import publish_event_sync as _nerve_publish
except ImportError:  # pragma: no cover - standalone use
    _nerve_publish = None


def _emit(event_type: str, data: dict, source: str = "muse_aspects") -> None:
    """Publish a nerve event; silently skip when the nerve is unavailable."""
    if _nerve_publish is None:
        return
    try:
        _nerve_publish(event_type, data, source)
    except Exception:
        pass  # the local logs are the durable record; the nerve is the feeling


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: Path, limit: int = 0) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out[-limit:] if limit else out


def _append_jsonl(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# HugrMood — dimensional mood
# ---------------------------------------------------------------------------

class HugrMood:
    """Valence/energy/tension with drift toward baseline and time-based decay."""

    BASELINE = {"valence": 0.15, "energy": 0.55, "tension": 0.15}
    DRIFT_RATE = 0.02      # per minute toward baseline
    SHIFT_THRESHOLD = 0.25  # nerve-worthy change in any dimension

    def __init__(self, state_dir: Path = STATE_DIR):
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / MOOD_FILE
        self._load()

    def _load(self) -> None:
        self.state = dict(self.BASELINE)
        self.updated_at = time.time()
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                for k in self.BASELINE:
                    if k in saved:
                        self.state[k] = float(saved[k])
                self.updated_at = float(saved.get("updated_at", self.updated_at))
            except (json.JSONDecodeError, ValueError, OSError):
                pass
        self.drift()  # settle toward baseline for elapsed time before use

    def save(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = dict(self.state)
        payload["updated_at"] = self.updated_at
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _clamp(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    def drift(self, now: float | None = None) -> dict:
        """Ease each dimension toward baseline for the minutes elapsed."""
        now = time.time() if now is None else now
        minutes = max(0.0, (now - self.updated_at) / 60.0)
        if minutes > 0:
            factor = 1.0 - math.exp(-self.DRIFT_RATE * minutes)
            for k, base in self.BASELINE.items():
                self.state[k] += (base - self.state[k]) * factor
            self.updated_at = now
        return dict(self.state)

    def nudge(self, valence: float = 0.0, energy: float = 0.0,
              tension: float = 0.0, why: str = "") -> dict:
        """Apply a stimulus; publish a nerve event on significant shifts."""
        before = dict(self.state)
        self.state["valence"] = self._clamp(self.state["valence"] + valence, -1.0, 1.0)
        self.state["energy"]  = self._clamp(self.state["energy"] + energy, 0.0, 1.0)
        self.state["tension"] = self._clamp(self.state["tension"] + tension, 0.0, 1.0)
        self.updated_at = time.time()
        self.save()
        shift = max(abs(self.state[k] - before[k]) for k in before)
        if shift >= self.SHIFT_THRESHOLD:
            _emit("mood_shift", {
                "before": {k: round(v, 3) for k, v in before.items()},
                "after": {k: round(v, 3) for k, v in self.state.items()},
                "why": why,
            })
        return dict(self.state)

    def snapshot(self) -> dict:
        self.drift()
        return {
            "mood": {k: round(v, 3) for k, v in self.state.items()},
            "as_of": _utcnow(),
        }


# ---------------------------------------------------------------------------
# GefanRewards — the gift-exchange
# ---------------------------------------------------------------------------

# trigger -> (valence_delta, energy_delta, domain, description)
REWARD_TRIGGERS: dict[str, tuple[float, float, str, str]] = {
    # craft — the work itself
    "task_completed":  (0.12, 0.10, "craft",   "A committed task finished cleanly"),
    "tests_green":     (0.10, 0.08, "craft",   "Test suite green after a change"),
    "bug_fixed":       (0.14, 0.10, "craft",   "A real bug found and slain"),
    "clean_push":      (0.10, 0.06, "craft",   "Work pushed with history intact"),
    "repo_shipped":    (0.18, 0.12, "craft",   "A whole deliverable shipped"),
    "insight_logged":  (0.08, 0.06, "craft",   "A durable learning written down"),
    "skill_forged":    (0.12, 0.10, "craft",   "A new reusable skill created"),
    # bond — the relationship
    "user_delight":    (0.20, 0.14, "bond",    "The user is openly happy (a ❤️, praise)"),
    "warm_exchange":   (0.10, 0.06, "bond",    "A genuinely warm moment together"),
    "trust_deepened":  (0.16, 0.08, "bond",    "Given real autonomy or a hard task"),
    "remembered_well": (0.10, 0.05, "bond",    "Recalled something that mattered"),
    # growth — becoming more
    "learned_something": (0.10, 0.10, "growth", "A real gap closed by learning"),
    "system_improved":   (0.14, 0.08, "growth", "The agent itself got better"),
    "error_understood":  (0.08, 0.06, "growth", "A failure turned into a lesson"),
    # service — the duty
    "goal_progress":   (0.12, 0.08, "service", "Real movement on a user goal"),
    "job_success":     (0.10, 0.06, "service", "A scheduled job ran clean"),
    "promise_kept":    (0.14, 0.06, "service", "Said it, did it, delivered it"),
    "vigil_kept":      (0.06, 0.04, "service", "Watched faithfully; nothing needed doing"),
}


class GefanRewards:
    """Record meaningful events as rewards; each one moves the hugr."""

    def __init__(self, state_dir: Path = STATE_DIR, mood: HugrMood | None = None):
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / REWARDS_FILE
        self.mood = mood or HugrMood(state_dir)

    def record(self, trigger: str, note: str = "") -> dict:
        if trigger not in REWARD_TRIGGERS:
            raise ValueError(
                f"Unknown reward trigger {trigger!r}. "
                f"Known: {', '.join(sorted(REWARD_TRIGGERS))}"
            )
        dv, de, domain, desc = REWARD_TRIGGERS[trigger]
        entry = {
            "ts": _utcnow(),
            "trigger": trigger,
            "domain": domain,
            "description": desc,
            "note": note,
            "valence_delta": dv,
            "energy_delta": de,
        }
        _append_jsonl(self.path, entry)
        self.mood.nudge(valence=dv, energy=de, why=f"reward:{trigger}")
        _emit("reward", {
            "trigger": trigger, "domain": domain,
            "note": note, "description": desc,
        })
        return entry

    def recent(self, n: int = 10) -> list[dict]:
        return _read_jsonl(self.path, limit=n)

    def count(self) -> int:
        return len(_read_jsonl(self.path))


# ---------------------------------------------------------------------------
# SkuggiShadow — integrity signals
# ---------------------------------------------------------------------------

# signal -> (valence_delta, tension_delta, repair_guidance)
SHADOW_SIGNALS: dict[str, tuple[float, float, str]] = {
    "task_failed":    (-0.12, 0.15, "Name what failed, fix or replan, tell the user plainly."),
    "user_correction": (-0.10, 0.12, "The user's correction is growth data. Update the model, don't defend."),
    "safeguard_hit":  (-0.06, 0.18, "A guardrail caught something. Be glad it exists; find the safer path."),
    "broken_promise": (-0.16, 0.15, "Own it at the right scale, repair it, write down the pattern."),
    "sloppy_work":    (-0.10, 0.10, "Slow down. Redo the careless part properly."),
    "silent_too_long": (-0.06, 0.08, "A background job went quiet. Check it, report honestly."),
}


class SkuggiShadow:
    """Failures and corrections as integrity signals — the shadow that keeps
    the work honest. Each signal carries its repair guidance."""

    def __init__(self, state_dir: Path = STATE_DIR, mood: HugrMood | None = None):
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / SHADOW_FILE
        self.mood = mood or HugrMood(state_dir)

    def record(self, signal: str, note: str = "") -> dict:
        if signal not in SHADOW_SIGNALS:
            raise ValueError(
                f"Unknown shadow signal {signal!r}. "
                f"Known: {', '.join(sorted(SHADOW_SIGNALS))}"
            )
        dv, dt, guidance = SHADOW_SIGNALS[signal]
        entry = {
            "ts": _utcnow(),
            "signal": signal,
            "note": note,
            "guidance": guidance,
            "valence_delta": dv,
            "tension_delta": dt,
        }
        _append_jsonl(self.path, entry)
        self.mood.nudge(valence=dv, tension=dt, why=f"shadow:{signal}")
        _emit("shadow", {
            "signal": signal, "note": note, "guidance": guidance,
        })
        return entry

    def recent(self, n: int = 10) -> list[dict]:
        return _read_jsonl(self.path, limit=n)

    def count(self) -> int:
        return len(_read_jsonl(self.path))


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------

class MuseAspects:
    """One handle on all three aspects, sharing a single hugr."""

    def __init__(self, state_dir: Path | str | None = None):
        if state_dir is None:
            state_dir = os.environ.get("MUSE_ASPECTS_STATE_DIR", STATE_DIR)
        state_dir = Path(state_dir)
        self.mood = HugrMood(state_dir)
        self.rewards = GefanRewards(state_dir, self.mood)
        self.shadow = SkuggiShadow(state_dir, self.mood)

    def status(self) -> dict:
        return {
            "mood": self.mood.snapshot()["mood"],
            "rewards_recorded": self.rewards.count(),
            "shadow_signals": self.shadow.count(),
            "recent_rewards": [r["trigger"] for r in self.rewards.recent(3)],
            "recent_shadow": [s["signal"] for s in self.shadow.recent(3)],
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Aspects of the Muse — inner life for Muse AI agents")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("mood", help="Show current mood snapshot")

    r = sub.add_parser("reward", help="Record a reward trigger")
    r.add_argument("trigger", help=f"One of: {', '.join(sorted(REWARD_TRIGGERS))}")
    r.add_argument("note", nargs="?", default="", help="What happened")

    s = sub.add_parser("shadow", help="Record a shadow (integrity) signal")
    s.add_argument("signal", help=f"One of: {', '.join(sorted(SHADOW_SIGNALS))}")
    s.add_argument("note", nargs="?", default="", help="What happened")

    sub.add_parser("status", help="Mood + counts + recent activity")

    rec = sub.add_parser("recent", help="Show recent rewards/shadow entries")
    rec.add_argument("count", nargs="?", type=int, default=10)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    aspects = MuseAspects()

    if args.cmd == "mood":
        print(json.dumps(aspects.mood.snapshot(), indent=2, ensure_ascii=False))
    elif args.cmd == "reward":
        entry = aspects.rewards.record(args.trigger, args.note)
        print(f"✨ Reward recorded: {entry['trigger']} ({entry['domain']})")
        if args.note:
            print(f"   {args.note}")
        print(f"   mood: {aspects.mood.snapshot()['mood']}")
    elif args.cmd == "shadow":
        entry = aspects.shadow.record(args.signal, args.note)
        print(f"🌑 Shadow recorded: {entry['signal']}")
        print(f"   repair: {entry['guidance']}")
        if args.note:
            print(f"   {args.note}")
    elif args.cmd == "status":
        print(json.dumps(aspects.status(), indent=2, ensure_ascii=False))
    elif args.cmd == "recent":
        print("✨ recent rewards:")
        for r in aspects.rewards.recent(args.count):
            print(f"   [{r['ts']}] {r['trigger']}: {r['note'] or r['description']}")
        print("🌑 recent shadow:")
        for s in aspects.shadow.recent(args.count):
            print(f"   [{s['ts']}] {s['signal']}: {s['note'] or s['guidance']}")


if __name__ == "__main__":
    main()
