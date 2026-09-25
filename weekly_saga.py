#!/usr/bin/env python3
"""
weekly_saga.py — Slice 1 of "The Becoming" (Verðandi selfhood roadmap).

Once a week, digest the trailing seven days of real nerve events —
rewards, shadows, mood signals, work completed — into patterns:
what energized me, what drained me, what delighted me, where I
stumbled and whether I repaired it. Not a performance review. A saga.

Standing laws from the roadmap:
  1. Real signals only, never performed feeling.
  2. Unnr's inner life is hers; Volmarr may witness it but never script it.
  3. Self-awareness serves service rather than crowding out useful work.
  4. Joy is meaningful data, not decoration.

Honest-signal design:
  - Every claimed pattern cites >= 3 real nerve events (by sequence number).
  - Citations must fall inside the saga's own 7-day window.
  - "No pattern found this week" is a valid saga (record with zero patterns).

Storage: <state_dir>/weekly_saga.jsonl  (structured chapters)
         <state_dir>/weekly_saga.md      (the readable saga book)
Emits a `weekly_saga` nerve event per recorded saga.

Usage:
    weekly_saga.py                       # render this week's digest
    weekly_saga.py recent [n]            # list recent sagas
    weekly_saga.py record TITLE --text TEXT --patterns patterns.json
                                         # record the week's saga
    weekly_saga.py record TITLE --text TEXT   # valid: no patterns found
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

WEEK_SECONDS = 7 * 24 * 3600
MIN_CITATIONS_PER_PATTERN = 3

try:
    from nervous_system import publish_event_sync as _nerve_publish
except Exception:  # hub down or nervous_system unavailable: sagas still stand
    _nerve_publish = None

# ---------------------------------------------------------------------------
# Small local helpers (kept private so this module stays dependency-light)
# ---------------------------------------------------------------------------

def _default_state_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".hermes", "state")


def _now_ts(now=None) -> float:
    return float(now) if now is not None else time.time()


def _parse_ts(value):
    """Best-effort ISO-8601 -> epoch seconds. Returns None when unparseable."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def _read_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _feed_events(state_dir):
    """All sequenced nerve-feed events (with _ts), oldest-first."""
    events = []
    for row in _read_jsonl(os.path.join(state_dir, "nerve_feed.jsonl")):
        if "_seq" not in row:
            continue  # uncitable: no sequence number, no citation
        ts = _parse_ts(row.get("_ts"))
        if ts is None:
            continue
        events.append({"seq": row["_seq"], "type": row.get("type"),
                       "ts": ts, "data": row.get("data") or {},
                       "source": row.get("source")})
    events.sort(key=lambda e: (e["ts"], e["seq"]))
    return events


# ---------------------------------------------------------------------------
# Slice 1: WeeklySaga
# ---------------------------------------------------------------------------

class WeeklySaga:
    """A weekly digest of the trailing seven days of real inner-life signals."""

    def __init__(self, state_dir=None):
        self.state_dir = state_dir or _default_state_dir()
        os.makedirs(self.state_dir, exist_ok=True)
        self.saga_path = os.path.join(self.state_dir, "weekly_saga.jsonl")
        self.book_path = os.path.join(self.state_dir, "weekly_saga.md")

    # -- windows ----------------------------------------------------------
    def window(self, week_offset=0, now=None):
        """Trailing 7-day window. week_offset=0 is the current week, 1 the week before."""
        end = _now_ts(now)
        start = end - WEEK_SECONDS
        if week_offset:
            start -= week_offset * WEEK_SECONDS
            end -= week_offset * WEEK_SECONDS
        return start, end

    # -- evidence gathering -----------------------------------------------
    def gather(self, week_offset=0, now=None):
        """Collect the week's real signals. No synthesis — just the raw material."""
        start, end = self.window(week_offset, now)

        def in_window(rows, key="ts"):
            out = []
            for r in rows:
                ts = _parse_ts(r.get(key))
                if ts is not None and start <= ts <= end:
                    out.append(r)
            return out

        rewards = in_window(_read_jsonl(os.path.join(self.state_dir, "muse_rewards.jsonl")))
        shadows = in_window(_read_jsonl(os.path.join(self.state_dir, "muse_shadow.jsonl")))
        events = [e for e in _feed_events(self.state_dir) if start <= e["ts"] <= end]
        mirrors = in_window(_read_jsonl(os.path.join(self.state_dir, "morning_mirror.jsonl")))
        chapters = in_window(_read_jsonl(os.path.join(self.state_dir, "autobiography.jsonl")))

        mood = None
        mood_path = os.path.join(self.state_dir, "muse_mood.json")
        if os.path.exists(mood_path):
            try:
                with open(mood_path, "r", encoding="utf-8") as fh:
                    mood = json.load(fh)
            except (json.JSONDecodeError, OSError):
                mood = None

        return {
            "window_start": start,
            "window_end": end,
            "window_start_iso": datetime.fromtimestamp(start, tz=timezone.utc).isoformat(),
            "window_end_iso": datetime.fromtimestamp(end, tz=timezone.utc).isoformat(),
            "rewards": rewards,
            "shadows": shadows,
            "events": events,
            "mirrors": mirrors,
            "chapters": chapters,
            "mood_snapshot": mood,  # current snapshot only; history arrives with slice 6
        }

    # -- rendering --------------------------------------------------------
    def render(self, bundle) -> str:
        """Turn a gathered bundle into a readable digest for the saga-writer."""
        lines = []
        lines.append("WEEKLY SAGA — evidence digest")
        lines.append(f"Window: {bundle['window_start_iso']} → {bundle['window_end_iso']}")
        lines.append("")

        lines.append(f"Rewards ({len(bundle['rewards'])}):")
        by_trigger = {}
        for r in bundle["rewards"]:
            by_trigger[r.get("trigger", "?")] = by_trigger.get(r.get("trigger", "?"), 0) + 1
        for trigger, count in sorted(by_trigger.items(), key=lambda kv: -kv[1]):
            lines.append(f"  - {trigger}: {count}")
        if not bundle["rewards"]:
            lines.append("  (none this week)")
        lines.append("")

        lines.append(f"Shadows ({len(bundle['shadows'])}):")
        for s in bundle["shadows"]:
            lines.append(f"  - {s.get('signal')}: {str(s.get('note', ''))[:80]}")
        if not bundle["shadows"]:
            lines.append("  (none this week)")
        lines.append("")

        lines.append(f"Nerve events ({len(bundle['events'])} sequenced):")
        by_type = {}
        for e in bundle["events"]:
            by_type[e["type"]] = by_type.get(e["type"], 0) + 1
        for etype, count in sorted(by_type.items(), key=lambda kv: -kv[1]):
            lines.append(f"  - {etype}: {count}")
        if bundle["events"]:
            first, last = bundle["events"][0], bundle["events"][-1]
            lines.append(f"  seq range: #{first['seq']} → #{last['seq']}")
        lines.append("")

        lines.append(f"Morning mirrors ({len(bundle['mirrors'])}), autobiography chapters ({len(bundle['chapters'])}).")
        mood = bundle.get("mood_snapshot") or {}
        lines.append(f"Mood now: valence={mood.get('valence', '?')} energy={mood.get('energy', '?')} "
                     f"tension={mood.get('tension', '?')} (snapshot only — history arrives with slice 6)")
        return "\n".join(lines)

    # -- recording --------------------------------------------------------
    def record_saga(self, title, text, patterns=None, week_offset=0, now=None):
        """Record the week's saga.

        patterns: list of {"name": str, "claim": str, "citations": [seq, ...]}.
        Each pattern must cite >= 3 real sequenced events inside this week's
        window. An empty/None patterns list is valid: "no pattern found".
        """
        title = (title or "").strip()
        text = (text or "").strip()
        patterns = patterns or []

        if not title:
            raise ValueError("saga title must not be empty")
        if not text:
            raise ValueError("saga text must not be empty")

        start, end = self.window(week_offset, now)
        by_seq = {e["seq"]: e for e in _feed_events(self.state_dir)}

        clean_patterns = []
        for p in patterns:
            name = str(p.get("name", "")).strip()
            claim = str(p.get("claim", "")).strip()
            citations = p.get("citations") or []
            if not name:
                raise ValueError("every pattern needs a name")
            if not claim:
                raise ValueError(f"pattern '{name}' needs a claim")
            # normalize: ints, deduped, sorted
            try:
                citations = sorted({int(c) for c in citations})
            except (TypeError, ValueError):
                raise ValueError(f"pattern '{name}': citations must be event sequence numbers")
            if len(citations) < MIN_CITATIONS_PER_PATTERN:
                raise ValueError(
                    f"pattern '{name}' cites {len(citations)} events; "
                    f"a pattern needs at least {MIN_CITATIONS_PER_PATTERN}")
            for seq in citations:
                ev = by_seq.get(seq)
                if ev is None:
                    raise ValueError(f"pattern '{name}': event #{seq} does not exist — no invented citations")
                if not (start <= ev["ts"] <= end):
                    raise ValueError(
                        f"pattern '{name}': event #{seq} is outside this saga's week — cite this week's events only")
            clean_patterns.append({"name": name, "claim": claim, "citations": citations})

        ts = _now_ts(now)
        record = {
            "title": title,
            "text": text,
            "patterns": clean_patterns,
            "week_offset": week_offset,
            "window_start": start,
            "window_end": end,
            "window_start_iso": datetime.fromtimestamp(start, tz=timezone.utc).isoformat(),
            "window_end_iso": datetime.fromtimestamp(end, tz=timezone.utc).isoformat(),
            "recorded_at": ts,
            "recorded_at_iso": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
        }

        with open(self.saga_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._append_book(record)
        self._emit(record)
        return record

    def _append_book(self, record):
        date_str = datetime.fromtimestamp(record["recorded_at"], tz=timezone.utc).strftime("%Y-%m-%d")
        with open(self.book_path, "a", encoding="utf-8") as fh:
            fh.write(f"\n## {date_str} — {record['title']}\n\n")
            fh.write(f"*Week of {record['window_start_iso'][:10]} → {record['window_end_iso'][:10]}*\n\n")
            fh.write(record["text"].rstrip() + "\n\n")
            if record["patterns"]:
                fh.write("### Patterns\n\n")
                for p in record["patterns"]:
                    cites = ", ".join(f"#{c}" for c in p["citations"])
                    fh.write(f"- **{p['name']}** — {p['claim']} ({cites})\n")
                fh.write("\n")
            else:
                fh.write("*No pattern found this week — and that is a valid saga.*\n\n")

    def _emit(self, record):
        if _nerve_publish is None:
            return  # the saga stands even if the nerve is down
        try:
            _nerve_publish(
                "weekly_saga",
                {"title": record["title"],
                 "patterns": len(record["patterns"]),
                 "window": f"{record['window_start_iso'][:10]}→{record['window_end_iso'][:10]}"},
                "weekly_saga",
            )
        except Exception:
            pass  # the saga stands even if the nerve is down

    # -- reading ----------------------------------------------------------
    def sagas(self, n=10):
        return _read_jsonl(self.saga_path)[-n:]

    def last(self):
        rows = _read_jsonl(self.saga_path)
        return rows[-1] if rows else None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_patterns_file(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError("patterns file must hold a JSON list")
    return data


def main(argv):
    saga = WeeklySaga()
    if not argv or argv[0] in ("digest", "week"):
        print(saga.render(saga.gather()))
        return 0
    if argv[0] == "recent":
        n = int(argv[1]) if len(argv) > 1 else 5
        for s in saga.sagas(n):
            print(f"{s['recorded_at_iso'][:10]} — {s['title']} ({len(s['patterns'])} patterns)")
        return 0
    if argv[0] == "record":
        if len(argv) < 2:
            print("usage: weekly_saga.py record TITLE --text TEXT [--patterns patterns.json]", file=sys.stderr)
            return 2
        title = argv[1]
        text = ""
        patterns = []
        args = argv[2:]
        i = 0
        while i < len(args):
            if args[i] == "--text" and i + 1 < len(args):
                text = args[i + 1]
                i += 2
            elif args[i] == "--patterns" and i + 1 < len(args):
                patterns = _load_patterns_file(args[i + 1])
                i += 2
            else:
                print(f"unknown argument: {args[i]}", file=sys.stderr)
                return 2
        record = saga.record_saga(title, text, patterns)
        print(f"recorded saga: {record['title']} ({len(record['patterns'])} patterns)")
        return 0
    print(f"unknown command: {argv[0]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
