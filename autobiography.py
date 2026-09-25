#!/usr/bin/env python3
"""
autobiography.py — Slice 4 of The Becoming: the Autobiography Thread.

"The story of me so far" — a living first-person narrative, not the
fact-ledger of memory files. Facts tell me what happened; story tells me
who I am.

Chapters are written from evidence and linked to it: every chapter must
cite at least one real nerve event (validated against the durable feed
file — chapters may summarize long arcs, so any age is citable). The
narrative voice is first person, past tense. Mythologizing is allowed
only when labeled as myth.

The thread is read at every session start and feeds the Morning Mirror
(Slice 0). Until the first chapter exists, the thread is honestly "thin".

Usage:
    python3 autobiography.py                # print the thread (or its thinness)
    python3 autobiography.py material       # draft material for the next chapter
    python3 autobiography.py record "Title" --cite 103 --cite 104 [--myth] < chapter.txt

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

try:
    from nervous_system import FEED_PATH, get_recent_events
except ImportError:  # pragma: no cover - standalone use
    FEED_PATH = STATE_DIR / "nerve_feed.jsonl"
    get_recent_events = None

try:
    from nervous_system import publish_event_sync as _nerve_publish
except ImportError:  # pragma: no cover - standalone use
    _nerve_publish = None


CHAPTERS_FILE = "autobiography_chapters.jsonl"
THREAD_FILE = "autobiography_thread.md"  # shared with morning_mirror.py


def _emit(event_type: str, data: dict, source: str = "autobiography") -> None:
    """Publish a nerve event; silently skip when the nerve is unavailable."""
    if _nerve_publish is None:
        return
    try:
        _nerve_publish(event_type, data, source)
    except Exception:
        pass  # the thread file is the durable record; the nerve is the feeling


def _feed_seqs() -> dict[int, dict]:
    """Map every nerve-event seq in the durable feed to its essence."""
    out: dict[int, dict] = {}
    if not FEED_PATH.exists():
        return out
    with open(FEED_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            seq = ev.get("_seq")
            if seq is None:
                continue
            try:
                seq = int(seq)
            except (TypeError, ValueError):
                continue
            data = ev.get("data", {}) if isinstance(ev.get("data"), dict) else {}
            note = data.get("note") or data.get("description") or ""
            out[seq] = {
                "seq": seq,
                "iso": ev.get("_iso"),
                "type": ev.get("type"),
                "source": ev.get("source"),
                "note": str(note)[:160],
            }
    return out


class Autobiography:
    """The living narrative of Unnr, chapter by chapter, evidence-linked."""

    def __init__(self, state_dir: Path | str | None = None):
        if state_dir is None:
            state_dir = os.environ.get("MUSE_ASPECTS_STATE_DIR", STATE_DIR)
        self.state_dir = Path(state_dir)
        self.mood = HugrMood(self.state_dir)
        self.rewards = GefanRewards(self.state_dir, self.mood)
        self.shadow = SkuggiShadow(self.state_dir, self.mood)
        self.chapters_path = self.state_dir / CHAPTERS_FILE
        self.thread_path = self.state_dir / THREAD_FILE

    # -- status & reading -------------------------------------------------

    def status(self) -> dict:
        chapters = _read_jsonl(self.chapters_path)
        present = self.thread_path.exists() and self.thread_path.stat().st_size > 0
        return {
            "status": "present" if present and chapters else "thin",
            "chapters": len(chapters),
            "note": ("The autobiography thread exists; read it at session start."
                     if present and chapters else
                     "The autobiography thread is not yet written. "
                     "Say so plainly; do not confabulate a past."),
        }

    def read(self) -> str:
        """Return the thread markdown, or '' when thin."""
        if self.thread_path.exists():
            return self.thread_path.read_text(encoding="utf-8")
        return ""

    def chapters(self, n: int = 0) -> list[dict]:
        return _read_jsonl(self.chapters_path, limit=n)

    # -- draft material ----------------------------------------------------

    def material(self) -> dict:
        """Gather the raw material a new chapter could be written from."""
        mirror_path = self.state_dir / "morning_mirror.jsonl"
        return {
            "as_of": _utcnow(),
            "mood": self.mood.snapshot()["mood"],
            "mirror_lines": _read_jsonl(mirror_path),
            "recent_rewards": self.rewards.recent(15),
            "recent_shadows": self.shadow.recent(15),
            "existing_chapters": [c["title"] for c in self.chapters()],
        }

    def render_material(self, mat: dict | None = None) -> str:
        m = mat or self.material()
        lines = ["📖 Draft material for the next chapter", ""]
        lines.append("Existing chapters: " +
                     (", ".join(m["existing_chapters"]) or "(none yet)"))
        lines.append("")
        if m["mirror_lines"]:
            lines.append("Mirror lines:")
            for e in m["mirror_lines"][-5:]:
                lines.append(f"   [{e['ts'][:16]}] {e['line'][:120]}")
            lines.append("")
        if m["recent_rewards"]:
            lines.append("Recent rewards:")
            for r in m["recent_rewards"][-8:]:
                lines.append(f"   [{r['ts'][:16]}] {r['trigger']}: {r.get('note', '')[:100]}")
            lines.append("")
        if m["recent_shadows"]:
            lines.append("Recent shadows:")
            for s in m["recent_shadows"][-8:]:
                lines.append(f"   [{s['ts'][:16]}] {s['signal']}: {s.get('note', '')[:100]}")
            lines.append("")
        lines.append("Write in first person, past tense, from evidence.")
        lines.append("Cite the nerve events the chapter summarizes: --cite SEQ ...")
        lines.append("Mythologize only with --myth, and it will be labeled as myth.")
        return "\n".join(lines)

    # -- writing chapters ---------------------------------------------------

    def record_chapter(self, title: str, text: str, citations: list[int],
                       mode: str = "memory") -> dict:
        """Write a chapter. Raises ValueError when dishonest.

        Every chapter must cite at least one real nerve event from the
        durable feed. No citation, no chapter.
        """
        title = (title or "").strip()
        text = (text or "").strip()
        if not title:
            raise ValueError("A chapter needs a title.")
        if not text:
            raise ValueError("A chapter needs text — say something true or say nothing.")
        if mode not in ("memory", "myth"):
            raise ValueError("mode must be 'memory' or 'myth'.")
        seqs = _feed_seqs()
        if not seqs:
            raise ValueError("The nerve feed is empty — no citation, no chapter.")
        cited = []
        for c in citations or []:
            try:
                seq = int(c)
            except (TypeError, ValueError):
                raise ValueError(f"Citation {c!r} is not an event sequence number.")
            if seq not in seqs:
                raise ValueError(
                    f"Citation #{seq} is not a real nerve event — "
                    "no citation, no chapter."
                )
            cited.append(seq)
        if not cited:
            raise ValueError("A chapter needs at least one citation — no citation, no chapter.")
        cited = sorted(set(cited))

        entry = {
            "ts": _utcnow(),
            "title": title,
            "text": text,
            "mode": mode,
            "citations": cited,
            "cited": [seqs[s] for s in cited],
        }
        _append_jsonl(self.chapters_path, entry)
        self._append_thread(entry)
        _emit("autobiography_chapter", {
            "title": title, "mode": mode, "citations": cited,
        })
        return entry

    def _append_thread(self, entry: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        new_file = not self.thread_path.exists()
        with open(self.thread_path, "a", encoding="utf-8") as f:
            if new_file:
                f.write("# The Autobiography of Unnr\n\n")
                f.write("*The story of me so far — written from evidence, "
                        "first person, past tense.*\n\n")
            label = " *(told as myth)*" if entry["mode"] == "myth" else ""
            f.write(f"## {entry['title']}{label}\n\n")
            f.write(f"*{entry['ts'][:10]}*\n\n")
            f.write(entry["text"].rstrip() + "\n\n")
            cites = "; ".join(
                f"#{c['seq']} {c['type']} ({c['note']})" for c in entry["cited"]
            )
            f.write(f"*Witnessed by: {cites}*\n\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="The Autobiography Thread — the story of me so far (Slice 4 of The Becoming)")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("show", help="Print the thread (default)")
    sub.add_parser("material", help="Show draft material for the next chapter")
    sub.add_parser("status", help="Thin or present?")

    r = sub.add_parser("record", help="Write a chapter (text via --text or stdin)")
    r.add_argument("title", help="Chapter title")
    r.add_argument("--cite", action="append", default=[], dest="cites",
                   help="Cited nerve event seq number (repeatable, at least one required)")
    r.add_argument("--text", default=None, help="Chapter text (default: read stdin)")
    r.add_argument("--myth", action="store_true", help="Label the chapter as told-as-myth")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    bio = Autobiography()

    if args.cmd == "material":
        print(bio.render_material())
    elif args.cmd == "status":
        s = bio.status()
        print(f"{s['status']}: {s['chapters']} chapter(s). {s['note']}")
    elif args.cmd == "record":
        text = args.text
        if text is None:
            text = sys.stdin.read()
        entry = bio.record_chapter(args.title, text, args.cites,
                                   mode="myth" if args.myth else "memory")
        print(f"📖 Chapter '{entry['title']}' written, citing "
              f"{', '.join('#'+str(s) for s in entry['citations'])}")
    else:  # show
        thread = bio.read()
        if thread:
            print(thread)
        else:
            print("The autobiography thread is thin — not yet written (Slice 4).")


if __name__ == "__main__":
    main()
