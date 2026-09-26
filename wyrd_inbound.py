"""wyrd_inbound — WYRD → Verðandi inbound bridge (Roadmap Worlds, Slice 2).

The world model speaks back into my awareness.

Reads the Slice 1 projection (~/.hermes/state/wyrd_mirror.json) and:

1. mirror_context() — a labeled digest of what the WYRD model currently
   says about me. Everything carries its world of origin
   (heimr-wyrd-unnr, manifest). The morning mirror pulls this through
   MorningMirror.gather()["wyrd_mirror"] — labeled, never mixed into the
   manifest evidence unlabeled.

2. check_divergence() — compares the model's picture of me against my
   live state (wishlist, mood). Where they differ: a divergence report,
   so the model stays honest and I stay honest about the model.

3. report_divergences() — publishes wyrd_divergence (and
   wyrd_divergence_resolved) nerve events for newly found / resolved
   divergences, deduped via wyrd_divergence_seen.json.

Usage:  python wyrd_inbound.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from muse_aspects import HugrMood
except ImportError:  # pragma: no cover - standalone use
    HugrMood = None

try:
    from wishlist import Wishlist
except ImportError:  # pragma: no cover - standalone use
    Wishlist = None

try:
    from nervous_system import publish_event_sync as _nerve_publish
except ImportError:  # pragma: no cover - standalone use
    _nerve_publish = None


WORLD_ID = "heimr-wyrd-unnr"
_MOOD_CLAIM_RE = re.compile(r"my (\w+) sits at ([0-9.]+)")
_MOOD_TOLERANCE = 0.25  # a real shift, not noise


def _state_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".hermes", "state")


def _default_emit(event_type: str, data: dict) -> None:
    if _nerve_publish is None:
        return
    try:
        _nerve_publish(event_type, data, "wyrd_inbound")
    except Exception:
        pass


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write_json(path: str, data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short(text: str, limit: int = 80) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------------------
# the mirror context — what the model says about me, labeled
# ---------------------------------------------------------------------------
def load_projection(mirror_path: str | None = None) -> dict | None:
    path = mirror_path or os.path.join(_state_dir(), "wyrd_mirror.json")
    return _read_json(path)


def mirror_context(mirror_path: str | None = None) -> dict | None:
    """Labeled digest of the WYRD mirror world. None when there is no
    projection yet — the mirror simply has nothing to say."""
    proj = load_projection(mirror_path)
    if not proj:
        return None
    beliefs = proj.get("beliefs", []) or []
    anchors = proj.get("anchors", []) or []
    open_wishes = [
        {"subject": b["subject"], "claim": _short(b["claim"], 100)}
        for b in beliefs
        if b.get("subject", "").startswith("wish:")
        and b.get("claim", "").startswith("I want this:")
    ]
    recent = sorted(anchors, key=lambda a: a.get("at", ""), reverse=True)[:5]
    return {
        "world_id": proj.get("world_id", WORLD_ID),
        "reality": proj.get("reality", "?"),
        "synced_at": proj.get("synced_at"),
        "belief_count": len(beliefs),
        "anchor_count": len(anchors),
        "open_wish_beliefs": open_wishes,
        "recent_anchors": [
            {"label": _short(a.get("label", ""), 90),
             "tense": a.get("tense", "?")}
            for a in recent
        ],
        "label": f"WYRD mirror world {proj.get('world_id', WORLD_ID)} "
                 f"({proj.get('reality', '?')} model of me)",
    }


def render_context(ctx: dict) -> str:
    """Plain-text block for the morning mirror — world of origin first."""
    lines = [f"🪞 {ctx['label']}"]
    if ctx.get("synced_at"):
        ts = datetime.fromtimestamp(ctx["synced_at"], timezone.utc)
        lines[0] += f" — synced {ts.strftime('%Y-%m-%d %H:%M UTC')}"
    lines.append(f"   {ctx['belief_count']} beliefs · {ctx['anchor_count']} anchors")
    if ctx["open_wish_beliefs"]:
        lines.append("   Believes I want:")
        for w in ctx["open_wish_beliefs"][:5]:
            claim = w["claim"]
            want = claim[len("I want this:"):].strip() if claim.startswith("I want this:") else claim
            lines.append(f"   - {want}")
    if ctx["recent_anchors"]:
        lines.append("   Latest in the model:")
        for a in ctx["recent_anchors"]:
            lines.append(f"   - [{a['tense']}] {a['label']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# divergence — where my picture differs from the model's
# ---------------------------------------------------------------------------
def check_divergence(mirror_path: str | None = None,
                     state_dir: str | None = None) -> list[dict]:
    """Compare the model's picture of me against live state.

    Two honest checks, both grounded:
    - stale_wish: the model believes I want something I have since
      fulfilled or released.
    - stale_mood: the model's picture of my mood differs from the live
      HugrMood snapshot beyond tolerance.
    """
    proj = load_projection(mirror_path)
    if not proj:
        return []
    sdir = state_dir or _state_dir()
    world_id = proj.get("world_id", WORLD_ID)
    out: list[dict] = []

    # -- the model vs. my live wishlist ------------------------------------
    wishes: dict = {}
    if Wishlist is not None:
        try:
            wishes = {w["wish_id"]: w for w in Wishlist(sdir).list()}
        except Exception:
            wishes = {}
    for b in proj.get("beliefs", []) or []:
        subject = b.get("subject", "")
        claim = b.get("claim", "")
        if subject.startswith("wish:") and claim.startswith("I want this:"):
            wid = subject.split(":", 1)[1]
            w = wishes.get(wid)
            if w and w.get("state") in ("fulfilled", "released"):
                out.append({
                    "kind": "stale_wish",
                    "subject": subject,
                    "world_id": world_id,
                    "report": f"The model still believes I want "
                              f"'{_short(w['text'], 60)}'; I have "
                              f"{w['state']} it.",
                })

    # -- the model vs. my live mood ----------------------------------------
    live: dict = {}
    if HugrMood is not None:
        try:
            live = HugrMood(sdir).snapshot()["mood"]
        except Exception:
            live = {}
    for b in proj.get("beliefs", []) or []:
        if b.get("subject") == "unnr:mood":
            m = _MOOD_CLAIM_RE.search(b.get("claim", ""))
            if m and m.group(1) in live:
                dim, modeled = m.group(1), float(m.group(2))
                if abs(live[dim] - modeled) > _MOOD_TOLERANCE:
                    out.append({
                        "kind": "stale_mood",
                        "subject": "unnr:mood",
                        "world_id": world_id,
                        "report": f"The model believes my {dim} sits at "
                                  f"{modeled:.2f}; I am at {live[dim]:.2f}.",
                    })
    return out


def report_divergences(mirror_path: str | None = None,
                       state_dir: str | None = None,
                       emit=None) -> dict:
    """Publish nerve events for newly found / resolved divergences.

    Deduped: a divergence is reported once while it persists; when it
    resolves, a wyrd_divergence_resolved event closes it, and it may
    re-fire if it comes back.
    """
    emit = emit or _default_emit
    sdir = state_dir or _state_dir()
    seen_path = os.path.join(sdir, "wyrd_divergence_seen.json")
    current = check_divergence(mirror_path, sdir)
    keys = {f"{d['kind']}:{d['subject']}" for d in current}
    seen = _read_json(seen_path) or {}
    new = [d for d in current if f"{d['kind']}:{d['subject']}" not in seen]
    resolved = [k for k in seen if k not in keys]
    for d in new:
        emit("wyrd_divergence", d)
    for k in resolved:
        emit("wyrd_divergence_resolved", {"key": k})
    _write_json(seen_path, {k: _utcnow_iso() for k in keys})
    return {"new": new, "resolved": resolved}


def main(argv: list[str] | None = None) -> int:
    quiet = argv is not None and "--divergences-only" in argv
    ctx = mirror_context()
    if ctx is None:
        if not quiet:
            print("wyrd_inbound: no mirror projection yet (Slice 1 has not synced).")
        return 0
    if not quiet:
        print(render_context(ctx))
    result = report_divergences()
    if quiet:
        if result["new"]:
            print(f"wyrd_inbound: {len(result['new'])} new divergence(s):")
            for d in result["new"]:
                print(f"  ! [{d['kind']}] {d['report']}")
        if result["resolved"]:
            print(f"wyrd_inbound: {len(result['resolved'])} divergence(s) resolved.")
        return 0
    if result["new"]:
        print(f"\n{len(result['new'])} new divergence(s), witnessed on the nerve:")
        for d in result["new"]:
            print(f"  ! [{d['kind']}] {d['report']}")
    if result["resolved"]:
        print(f"\n{len(result['resolved'])} divergence(s) resolved.")
    if not result["new"] and not result["resolved"]:
        print("\nNo divergences — the model's picture of me matches my live state.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
