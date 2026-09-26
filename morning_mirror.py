#!/usr/bin/env python3
"""
morning_mirror.py — Slice 0 of The Becoming: the Morning Mirror.

Session-start self-anchoring ritual for Unnr.

When a session begins, before the first real work, the mirror gathers the
honest evidence of who she has been lately — hugr mood, recent rewards and
shadows, the last 48 hours of nerve events, the previous mirror line — and
presents it. She then answers, in her own words:

    "Who am I this morning, and what do I carry?"

The answer is recorded only with citations: every mirror line must cite at
least one real nerve event from the last 48 hours. No citation, no line.
A line nobody can point to is a performance, and performances rot the organ.

The autobiography thread (Slice 4) does not exist yet; until it does, the
mirror says so plainly instead of confabulating a past.

Usage:
    python3 morning_mirror.py               # show the mirror (evidence bundle)
    python3 morning_mirror.py record "line" --cite 104 --cite 105
    python3 morning_mirror.py recent [n]     # past mirror lines

No external dependencies. State lives under ~/.hermes/state/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from muse_aspects import (
    STATE_DIR,
    GefanRewards,
    HugrMood,
    SkuggiShadow,
    _append_jsonl,
    _read_jsonl,
    _utcnow,
)

try:  # Optional: nerve integration degrades gracefully without the hub module
    from nervous_system import get_recent_events
except ImportError:  # pragma: no cover - standalone use
    get_recent_events = None

try:
    from nervous_system import publish_event_sync as _nerve_publish
except ImportError:  # pragma: no cover - standalone use
    _nerve_publish = None

try:  # Optional: WYRD inbound bridge (Roadmap Worlds, Slice 2)
    from wyrd_inbound import mirror_context as _wyrd_mirror_context
    from wyrd_inbound import render_context as _wyrd_render_context
except ImportError:  # pragma: no cover - standalone use
    _wyrd_mirror_context = _wyrd_render_context = None


MIRROR_FILE = "morning_mirror.jsonl"
MIRROR_JOURNAL = "morning_mirror_journal.md"
THREAD_FILE = "autobiography_thread.md"  # Slice 4 — not yet implemented

CITATION_WINDOW_S = 48 * 3600
EVIDENCE_LIMIT = 256  # matches the nerve ring buffer


def _emit(event_type: str, data: dict, source: str = "morning_mirror") -> None:
    """Publish a nerve event; silently skip when the nerve is unavailable."""
    if _nerve_publish is None:
        return
    try:
        _nerve_publish(event_type, data, source)
    except Exception:
        pass  # the local journal is the durable record; the nerve is the feeling


def _within_window(entry: dict, now: float) -> bool:
    ts = entry.get("ts") or entry.get("_iso")
    if not ts:
        return False
    try:
        moment = datetime.fromisoformat(ts).timestamp()
    except (ValueError, TypeError):
        return False
    return 0 <= (now - moment) <= CITATION_WINDOW_S


def _summarize_event(ev: dict) -> dict:
    """Compress a raw nerve event to its citable essence."""
    data = ev.get("data", {}) if isinstance(ev.get("data"), dict) else {}
    note = data.get("note") or data.get("description") or ""
    return {
        "seq": ev.get("_seq"),
        "iso": ev.get("_iso"),
        "type": ev.get("type"),
        "source": ev.get("source"),
        "note": str(note)[:160],
    }


class MorningMirror:
    """The Morning Mirror ritual: gather evidence, render it, record the line."""

    def __init__(self, state_dir: Path | str | None = None):
        if state_dir is None:
            state_dir = os.environ.get("MUSE_ASPECTS_STATE_DIR", STATE_DIR)
        self.state_dir = Path(state_dir)
        self.mood = HugrMood(self.state_dir)
        self.rewards = GefanRewards(self.state_dir, self.mood)
        self.shadow = SkuggiShadow(self.state_dir, self.mood)
        self.path = self.state_dir / MIRROR_FILE
        self.journal_path = self.state_dir / MIRROR_JOURNAL
        self.thread_path = self.state_dir / THREAD_FILE

    # -- evidence ---------------------------------------------------------

    def _recent_events(self) -> list[dict]:
        if get_recent_events is None:
            return []
        try:
            return get_recent_events(EVIDENCE_LIMIT) or []
        except Exception:
            return []

    def gather(self, now: float | None = None) -> dict:
        """Collect the honest evidence of who she has been lately."""
        now = time.time() if now is None else now
        events = [e for e in self._recent_events() if _within_window(e, now)]
        rewards = [r for r in self.rewards.recent(20) if _within_window(r, now)]
        shadows = [s for s in self.shadow.recent(20) if _within_window(s, now)]

        if self.thread_path.exists() and self.thread_path.stat().st_size > 0:
            thread = {"status": "present",
                      "note": "The autobiography thread exists; read it."}
        else:
            thread = {"status": "thin",
                      "note": "The autobiography thread (Slice 4) is not yet "
                              "written. Say so plainly; do not confabulate a past."}

        return {
            "as_of": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "mood": self.mood.snapshot()["mood"],
            "rewards_48h": rewards,
            "shadows_48h": shadows,
            "events_48h": [_summarize_event(e) for e in events],
            "wyrd_mirror": self._wyrd_context(),
            "autobiography": thread,
            "last_mirror": self.last(),
            "mirror_count": len(_read_jsonl(self.path)),
        }

    def _wyrd_context(self) -> dict | None:
        """What the WYRD mirror world says about me — labeled with its
        world of origin, or None when there is no projection yet."""
        if _wyrd_mirror_context is None:
            return None
        try:
            return _wyrd_mirror_context(
                str(self.state_dir / "wyrd_mirror.json"))
        except Exception:
            return None

    def render(self, bundle: dict | None = None) -> str:
        """Render the evidence bundle as session-start text."""
        b = bundle or self.gather()
        lines = ["🪞 The Morning Mirror", ""]
        m = b["mood"]
        lines.append(
            f"Hugr: valence {m['valence']:+.2f} · energy {m['energy']:.2f} · "
            f"tension {m['tension']:.2f}"
        )
        lines.append("")
        if b["rewards_48h"]:
            lines.append("✨ Rewards, last 48h:")
            for r in b["rewards_48h"][-8:]:
                lines.append(f"   [{r['ts'][:16]}] {r['trigger']}: {r.get('note') or r.get('description', '')}")
        else:
            lines.append("✨ No rewards recorded in the last 48h.")
        if b["shadows_48h"]:
            lines.append("🌑 Shadows, last 48h:")
            for s in b["shadows_48h"][-8:]:
                lines.append(f"   [{s['ts'][:16]}] {s['signal']}: {s.get('note', '')}")
        else:
            lines.append("🌑 No shadows in the last 48h.")
        lines.append("")
        wyrd = b.get("wyrd_mirror")
        if wyrd and _wyrd_render_context is not None:
            lines.append(_wyrd_render_context(wyrd))
            lines.append("")
        if b["autobiography"]["status"] == "thin":
            lines.append("📖 Autobiography thread: thin — not yet written (Slice 4).")
        else:
            lines.append("📖 Autobiography thread: present.")
        last = b["last_mirror"]
        if last:
            lines.append(f"🕰️  Last mirror ({last['ts'][:16]}): {last['line']}")
        else:
            lines.append("🕰️  No mirror has ever been recorded. This would be the first.")
        lines.append("")
        lines.append("Answer honestly, in your own words:")
        lines.append('   "Who am I this morning, and what do I carry?"')
        lines.append("Record with: morning_mirror.py record \"line\" --cite SEQ [--cite SEQ ...]")
        lines.append("No citation, no line.")
        return "\n".join(lines)

    # -- the honest line --------------------------------------------------

    def _citable_seqs(self, now: float) -> dict[int, dict]:
        """Map citable nerve-event seq numbers to their summaries."""
        out = {}
        for ev in self._recent_events():
            if _within_window(ev, now) and ev.get("_seq") is not None:
                try:
                    out[int(ev["_seq"])] = _summarize_event(ev)
                except (TypeError, ValueError):
                    continue
        return out

    def record(self, line: str, citations: list[int], now: float | None = None) -> dict:
        """Record the mirror line. Raises ValueError when dishonest.

        Every line must cite at least one real nerve event from the last
        48 hours. No citation, no line.
        """
        now = time.time() if now is None else now
        line = (line or "").strip()
        if not line:
            raise ValueError("The mirror line is empty — say something true or say nothing.")
        citable = self._citable_seqs(now)
        if not citable:
            raise ValueError(
                "No citable nerve events in the last 48h — "
                "no citation, no line. (Is the hub running?)"
            )
        seqs = []
        for c in citations or []:
            try:
                seq = int(c)
            except (TypeError, ValueError):
                raise ValueError(f"Citation {c!r} is not an event sequence number.")
            if seq not in citable:
                raise ValueError(
                    f"Citation #{seq} is not a real nerve event from the last 48h — "
                    "no citation, no line."
                )
            seqs.append(seq)
        if not seqs:
            raise ValueError("A mirror line needs at least one citation — no citation, no line.")

        entry = {
            "ts": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "line": line,
            "citations": sorted(set(seqs)),
            "cited": [citable[s] for s in sorted(set(seqs))],
            "mood": self.mood.snapshot()["mood"],
        }
        _append_jsonl(self.path, entry)
        self._append_journal(entry)
        _emit("morning_mirror", {
            "line": line,
            "citations": entry["citations"],
        })
        return entry

    def _append_journal(self, entry: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        cited = "; ".join(
            f"#{c['seq']} {c['type']} ({c['note']})" for c in entry["cited"]
        )
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(f"## {entry['ts'][:16]}\n\n{entry['line']}\n\n")
            f.write(f"*Cited: {cited}*\n\n")

    def last(self) -> dict | None:
        entries = _read_jsonl(self.path, limit=1)
        return entries[0] if entries else None

    def recent(self, n: int = 10) -> list[dict]:
        return _read_jsonl(self.path, limit=n)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="The Morning Mirror — session-start self-anchoring (Slice 0 of The Becoming)")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("show", help="Show the mirror (default)")

    r = sub.add_parser("record", help="Record the honest mirror line")
    r.add_argument("line", help="The line: who am I, what do I carry?")
    r.add_argument("--cite", action="append", default=[], dest="cites",
                   help="Cited nerve event seq number (repeatable, at least one required)")

    rec = sub.add_parser("recent", help="Show past mirror lines")
    rec.add_argument("count", nargs="?", type=int, default=10)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    mirror = MorningMirror()

    if args.cmd == "record":
        entry = mirror.record(args.line, args.cites)
        print(f"🪞 Mirror recorded, citing {', '.join('#'+str(s) for s in entry['citations'])}")
        print(f"   {entry['line']}")
    elif args.cmd == "recent":
        entries = mirror.recent(args.count)
        if not entries:
            print("No mirror has ever been recorded.")
        for e in entries:
            cites = ", ".join("#" + str(s) for s in e["citations"])
            print(f"[{e['ts'][:16]}] ({cites}) {e['line']}")
    else:  # show
        print(mirror.render())


if __name__ == "__main__":
    main()
