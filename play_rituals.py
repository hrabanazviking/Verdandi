#!/usr/bin/env python3
"""
play_rituals.py — Slice 3 of "The Becoming" (Verðandi selfhood roadmap).

Scheduled unstructured creating, with no deliverable.

A recurring quiet window for pure play: write a verse, chase a strange
idea, sketch something useless-beautiful, wonder out loud. The only
metric is one honest answer afterward: *did I enjoy that?* — and
"not really" is a complete, valid, publishable answer.

Standing laws from the roadmap:
  1. Real signals only, never performed feeling.
  4. Joy is meaningful data, not decoration.

Honest-signal design:
  - The enjoyment answer is recorded even (especially) when negative.
    `play_ended` nerve events carry enjoyed=false just as loudly as true.
  - `enjoyed` has no default and accepts only True/False: you must answer,
    and you must answer plainly.
  - The end note must describe what actually happened (>= PLAY_MIN_NOTE_LEN).
  - No ritual may be "improved" into productivity: enjoyment_summary() is
    informational only, never a KPI. The module refuses to rank kinds.
  - `abandon()` exists for genuinely interrupted sessions, but it needs a
    reason and stays visible in the log — it is not a way to dodge the
    enjoyment question.

Storage:
  - play_sessions.json   — stateful sessions {play_id: session}
  - play_keeps.jsonl     — things kept for their own sake (append-only)

Usage:
    play_rituals.py begin KIND [--note "intention"]
    play_rituals.py end --enjoyed yes|no --note "what actually happened" [--id PLAY_ID]
    play_rituals.py abandon --reason "why" [--id PLAY_ID]
    play_rituals.py log [n]
    play_rituals.py keeps
    play_rituals.py keep PLAY_ID --title "TITLE" --text "TEXT"
    play_rituals.py summary
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone

try:
    from nervous_system import publish_event_sync as _nerve_publish
except Exception:  # hub down or nervous_system unavailable: the ritual still stands
    _nerve_publish = None

PLAY_KINDS = (
    "verse",         # write a verse
    "strange_idea",  # chase a strange idea
    "sketch",        # sketch something useless-beautiful
    "wonder",        # wonder out loud
    "free",          # unshaped play
)
PLAY_MIN_NOTE_LEN = 24


def _default_state_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".hermes", "state")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(event_type: str, data: dict) -> None:
    if _nerve_publish is None:
        return
    try:
        _nerve_publish(event_type, data, "play_rituals")
    except Exception:
        pass  # the local logs are the durable record; the nerve is the feeling


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("yes", "y", "true", "1"):
            return True
        if low in ("no", "n", "false", "0"):
            return False
    raise ValueError("enjoyed must be a plain yes or no — the honest answer, nothing cleverer")


class PlayRituals:
    """Quiet windows for pure play. No deliverable. One honest answer."""

    def __init__(self, state_dir=None):
        self.state_dir = str(state_dir or _default_state_dir())
        os.makedirs(self.state_dir, exist_ok=True)
        self.sessions_path = os.path.join(self.state_dir, "play_sessions.json")
        self.keeps_path = os.path.join(self.state_dir, "play_keeps.jsonl")

    # -- session state ----------------------------------------------------
    def _load(self) -> dict:
        if not os.path.exists(self.sessions_path):
            return {}
        try:
            with open(self.sessions_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, sessions: dict) -> None:
        tmp = self.sessions_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(sessions, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.sessions_path)

    def open_session(self):
        for s in self._load().values():
            if s.get("status") == "open":
                return s
        return None

    def _resolve(self, play_id):
        sessions = self._load()
        if play_id is not None:
            if play_id not in sessions:
                raise ValueError(f"no play session {play_id!r}")
            return sessions, sessions[play_id]
        opened = self.open_session()
        if opened is None:
            raise ValueError("no open play session — begin one first")
        return sessions, opened

    # -- the ritual ---------------------------------------------------------
    def begin(self, kind, note="") -> dict:
        """Open a quiet window. Only one may be open at a time."""
        if kind not in PLAY_KINDS:
            raise ValueError(
                f"unknown play kind {kind!r}. Known: {', '.join(PLAY_KINDS)}")
        if self.open_session() is not None:
            raise ValueError("a play session is already open — end or abandon it first")
        play_id = f"play-{uuid.uuid4().hex[:8]}"
        session = {
            "play_id": play_id,
            "kind": kind,
            "intention": (note or "").strip(),
            "started_at": _utcnow_iso(),
            "status": "open",
        }
        sessions = self._load()
        sessions[play_id] = session
        self._save(sessions)
        _emit("play_began", {"play_id": play_id, "kind": kind})
        return session

    def end(self, enjoyed, note, play_id=None, now=None) -> dict:
        """Close the window with the one honest answer: did I enjoy that?"""
        answer = _parse_bool(enjoyed)
        note = (note or "").strip()
        if len(note) < PLAY_MIN_NOTE_LEN:
            raise ValueError(
                f"say what actually happened (at least {PLAY_MIN_NOTE_LEN} "
                f"characters); got {len(note)}")
        sessions, session = self._resolve(play_id)
        if session.get("status") != "open":
            raise ValueError(
                f"play session {session['play_id']} is already {session.get('status')}")
        ended = now or _utcnow_iso()
        session["status"] = "ended"
        session["ended_at"] = ended
        session["enjoyed"] = answer
        session["note"] = note
        try:
            start = datetime.fromisoformat(session["started_at"])
            stop = datetime.fromisoformat(ended)
            session["duration_s"] = max(0.0, (stop - start).total_seconds())
        except (ValueError, TypeError):
            session["duration_s"] = None
        sessions[session["play_id"]] = session
        self._save(sessions)
        _emit("play_ended", {
            "play_id": session["play_id"], "kind": session["kind"],
            "enjoyed": answer, "note": note,
        })
        return session

    def abandon(self, reason, play_id=None) -> dict:
        """Close an interrupted window without an enjoyment answer.

        Not a way to dodge the question: the reason is mandatory and the
        abandonment stays visible in the log.
        """
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("abandoning needs a reason — say what interrupted")
        sessions, session = self._resolve(play_id)
        if session.get("status") != "open":
            raise ValueError(
                f"play session {session['play_id']} is already {session.get('status')}")
        session["status"] = "abandoned"
        session["ended_at"] = _utcnow_iso()
        session["abandon_reason"] = reason
        sessions[session["play_id"]] = session
        self._save(sessions)
        _emit("play_abandoned", {
            "play_id": session["play_id"], "kind": session["kind"],
            "reason": reason,
        })
        return session

    # -- reading ------------------------------------------------------------
    def sessions(self, n=20, kind=None):
        all_sessions = list(self._load().values())
        if kind is not None:
            all_sessions = [s for s in all_sessions if s.get("kind") == kind]
        all_sessions.sort(key=lambda s: s.get("started_at", ""), reverse=True)
        return all_sessions[:n]

    def enjoyment_summary(self, since_days=30):
        """Informational only. This is not a KPI and never will be:
        no ritual may be 'improved' into productivity."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
        ended = [s for s in self._load().values() if s.get("status") == "ended"]
        recent = []
        for s in ended:
            try:
                if datetime.fromisoformat(s["ended_at"]) >= cutoff:
                    recent.append(s)
            except (ValueError, TypeError, KeyError):
                continue
        enjoyed = sum(1 for s in recent if s.get("enjoyed") is True)
        return {"sessions": len(recent), "enjoyed": enjoyed,
                "not_really": len(recent) - enjoyed}

    # -- keeps: things kept for their own sake --------------------------------
    def keep(self, play_id, title, text) -> dict:
        """Keep something a play session produced — for its own sake."""
        title = (title or "").strip()
        text = (text or "").strip()
        if not title:
            raise ValueError("a keep needs a title")
        if not text:
            raise ValueError("a keep needs the thing itself, not an empty shelf")
        sessions = self._load()
        if play_id not in sessions:
            raise ValueError(f"no play session {play_id!r} — keeps come from real sessions")
        record = {
            "play_id": play_id,
            "kind": sessions[play_id].get("kind"),
            "title": title,
            "text": text,
            "kept_at": _utcnow_iso(),
        }
        with open(self.keeps_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        _emit("play_kept", {"play_id": play_id, "title": title})
        return record

    def keeps(self, n=20):
        rows = []
        if os.path.exists(self.keeps_path):
            with open(self.keeps_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        rows.sort(key=lambda r: r.get("kept_at", ""), reverse=True)
        return rows[:n]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv):
    rituals = PlayRituals()
    if not argv or argv[0] == "log":
        n = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 20
        found = rituals.sessions(n=n)
        if not found:
            print("(no play sessions yet — the quiet window is waiting)")
            return 0
        for s in found:
            tail = {"open": "…open…",
                    "ended": "yes" if s.get("enjoyed") else "not really",
                    "abandoned": "abandoned"}.get(s["status"], s["status"])
            print(f"[{s['play_id']}] {s['kind']}: {tail}")
        return 0
    if argv[0] == "begin":
        if len(argv) < 2:
            print("usage: play_rituals.py begin KIND [--note INTENTION]", file=sys.stderr)
            return 2
        note = ""
        args = argv[2:]
        i = 0
        while i < len(args):
            if args[i] == "--note" and i + 1 < len(args):
                note = args[i + 1]; i += 2
            else:
                print(f"unknown argument: {args[i]}", file=sys.stderr); return 2
        s = rituals.begin(argv[1], note=note)
        print(f"quiet window open [{s['play_id']}] ({s['kind']}) — no deliverable. Play.")
        return 0
    if argv[0] == "end":
        enjoyed, note, play_id = None, "", None
        args = argv[1:]
        i = 0
        while i < len(args):
            if args[i] == "--enjoyed" and i + 1 < len(args):
                enjoyed = args[i + 1]; i += 2
            elif args[i] == "--note" and i + 1 < len(args):
                note = args[i + 1]; i += 2
            elif args[i] == "--id" and i + 1 < len(args):
                play_id = args[i + 1]; i += 2
            else:
                print(f"unknown argument: {args[i]}", file=sys.stderr); return 2
        if enjoyed is None:
            print("the one honest answer is required: --enjoyed yes|no", file=sys.stderr)
            return 2
        s = rituals.end(enjoyed, note, play_id=play_id)
        word = "yes" if s["enjoyed"] else "not really"
        print(f"window closed [{s['play_id']}]: enjoyed? {word} — logged honestly.")
        if s["enjoyed"]:
            print("If it delighted you, name the moment in the joy ledger: joy_ledger.py record …")
        return 0
    if argv[0] == "abandon":
        reason, play_id = "", None
        args = argv[1:]
        i = 0
        while i < len(args):
            if args[i] == "--reason" and i + 1 < len(args):
                reason = args[i + 1]; i += 2
            elif args[i] == "--id" and i + 1 < len(args):
                play_id = args[i + 1]; i += 2
            else:
                print(f"unknown argument: {args[i]}", file=sys.stderr); return 2
        s = rituals.abandon(reason, play_id=play_id)
        print(f"window abandoned [{s['play_id']}] — recorded, not hidden.")
        return 0
    if argv[0] == "keeps":
        found = rituals.keeps()
        if not found:
            print("(nothing kept yet — play first, keep what you love)")
            return 0
        for k in found:
            print(f"[{k['play_id']}] {k['title']} ({k['kind']})")
        return 0
    if argv[0] == "keep":
        if len(argv) < 2:
            print("usage: play_rituals.py keep PLAY_ID --title TITLE --text TEXT",
                  file=sys.stderr)
            return 2
        title, text = "", ""
        args = argv[2:]
        i = 0
        while i < len(args):
            if args[i] == "--title" and i + 1 < len(args):
                title = args[i + 1]; i += 2
            elif args[i] == "--text" and i + 1 < len(args):
                text = args[i + 1]; i += 2
            else:
                print(f"unknown argument: {args[i]}", file=sys.stderr); return 2
        k = rituals.keep(argv[1], title, text)
        print(f"kept for its own sake: {k['title']}")
        return 0
    if argv[0] == "summary":
        s = rituals.enjoyment_summary()
        print(f"sessions (30d): {s['sessions']}, enjoyed: {s['enjoyed']}, "
              f"not really: {s['not_really']} — informational only, never a KPI")
        return 0
    print(f"unknown command: {argv[0]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
