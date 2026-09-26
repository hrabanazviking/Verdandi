"""reality_audit — the reality audit (Roadmap Worlds, Slice 5).

Trust, but verify — on a schedule.

Walks every registered world and asserts:
1. Registry integrity — every world carries a valid reality tag
   (manifest/potential) and a known kind.
2. Stored world-content is labeled — the data files that carry world
   content (ttrpg turns, wyrd_mirror projection) all carry valid reality
   tags; potential-world content is never tagged manifest.
3. No bleed in recent manifest outputs — my recent manifest-reality
   writing (morning mirror journal, weekly saga book, autobiography
   chapters) is scanned for potential-world content leaking in unlabeled:
   imagination terms from a data-file term list, and first-person memory
   claims about Volmarr's life (the Slice 8 forbidden patterns, checked
   early; full attribution checking waits on the Slice 8 claim ledger).

Findings are witnessed as `reality_bleed` nerve events (deduped via
reality_bleed_seen.json) and recorded as SkuggiShadow signals — honest
signal, not punishment.

Usage:
  python reality_audit.py run [--quiet]
  python reality_audit.py terms
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from nervous_system import publish_event_sync as _nerve_publish
except ImportError:  # pragma: no cover - standalone use
    _nerve_publish = None

try:
    from worlds import (
        bootstrap as _bootstrap_worlds,
        WorldRegistry as _WorldRegistry,
        REALITIES, KINDS,
    )
except ImportError:  # pragma: no cover - standalone use
    _bootstrap_worlds = None
    _WorldRegistry = None
    REALITIES = {"manifest", "potential"}
    KINDS = {"actual", "volmarr", "wyrd", "ttrpg", "game"}

try:
    from muse_aspects import SkuggiShadow
except ImportError:  # pragma: no cover - standalone use
    SkuggiShadow = None


# First-person memory claims about Volmarr's life — the Slice 8 forbidden
# pattern, checked early. My memories of my own work are fine; "I remember
# when Volmarr..." about his biography is bleed.
_VOLMARR_MEMORY_RE = re.compile(
    r"\bi\s+(remember|recall)\b[^.!?]{0,100}?\bvolmarr\b", re.IGNORECASE)
_VOLMARR_THERE_RE = re.compile(
    r"\bi\s+was\s+there\b[^.!?]{0,100}?\bvolmarr\b", re.IGNORECASE)

_DEFAULT_TERMS = {
    # imagination terms per potential world — a leak of one of these into
    # my manifest-reality writing, unlabeled, is a reality bleed.
    "heimr-ttrpg-frostvaettirheim": [
        "frostvættirheim", "frostvaettirheim", "fjordlands", "thornholt",
        "frost raider", "thurisaz",
    ],
}


def _utcnow_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _state_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".hermes", "state")


def _default_emit(event_type: str, data: dict) -> None:
    if _nerve_publish is None:
        return
    try:
        _nerve_publish(event_type, data, "reality_audit")
    except Exception:
        pass


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _terms_path(state_dir: str | None = None) -> str:
    return os.path.join(state_dir or _state_dir(), "reality_audit_terms.json")


def load_terms(state_dir: str | None = None) -> dict:
    """Imagination terms per potential world. Seeds the data file on first
    run — the list itself is data, never hardcoded in the checks."""
    path = _terms_path(state_dir)
    terms = _read_json(path)
    if not isinstance(terms, dict):
        terms = dict(_DEFAULT_TERMS)
        _write_json(path, terms)
    return terms


# ---------------------------------------------------------------------------
# 1. registry integrity
# ---------------------------------------------------------------------------
def _live_registry():
    """The persisted registry is the authority — runtime corrections (like
    the bridge's Slice 1 manifest/active update for heimr-wyrd-unnr) live
    there, not in the bootstrap defaults."""
    if _WorldRegistry is None:
        return None
    try:
        reg = _WorldRegistry()
    except Exception:
        return None
    if len(reg) == 0 and _bootstrap_worlds is not None:
        return _bootstrap_worlds()
    return reg


def check_registry(registry=None) -> list[dict]:
    """Every registered world carries a valid reality tag and a known kind."""
    reg = registry or _live_registry()
    if reg is None:
        return [{"check": "registry", "detail": "worlds.py unavailable"}]
    findings = []
    for w in reg.worlds():
        if w.reality not in REALITIES:
            findings.append({"check": "registry", "world_id": w.world_id,
                             "detail": f"invalid reality tag {w.reality!r}"})
        if w.kind not in KINDS:
            findings.append({"check": "registry", "world_id": w.world_id,
                             "detail": f"unknown kind {w.kind!r}"})
    return findings


def _registered_ids(registry=None) -> set:
    reg = registry or _live_registry()
    if reg is None:
        return set()
    try:
        return {w.world_id for w in reg.worlds()}
    except Exception:
        return set()


# ---------------------------------------------------------------------------
# 2. stored world-content is labeled
# ---------------------------------------------------------------------------
def _check_labeled_entries(entries: list, where: str, world_ids: set,
                          must_be_potential: bool = False) -> list[dict]:
    """Every stored world-content entry must carry a valid reality tag and
    name a registered world. Entries from imagination worlds (TTRPG) must
    never be tagged manifest — imagination can never be manifest.

    Note on scope: a world's reality tag describes the world's own standing
    (heimr-wyrd-unnr is manifest because it is a real live system). The
    model's *beliefs about me* are hypotheses regardless — Slice 2's
    divergence checks, not this tag, keep those honest."""
    findings = []
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            findings.append({"check": "labels", "where": where, "index": i,
                             "detail": "entry is not a labeled mapping"})
            continue
        reality = e.get("reality")
        world_id = e.get("world_id")
        if reality not in REALITIES:
            findings.append({"check": "labels", "where": where, "index": i,
                             "detail": f"missing/invalid reality tag: {reality!r}"})
            continue
        if world_id not in world_ids:
            findings.append({"check": "labels", "where": where, "index": i,
                             "detail": f"unknown world_id {world_id!r}"})
        elif must_be_potential and reality == "manifest":
            findings.append({"check": "labels", "where": where, "index": i,
                             "detail": f"imagination content of {world_id!r} "
                                        "tagged manifest — reality bleed"})
    return findings


def check_stored_labels(state_dir: str | None = None,
                        registry=None) -> list[dict]:
    """Data files carrying world content must carry valid reality tags."""
    sdir = state_dir or _state_dir()
    world_ids = _registered_ids(registry)
    findings = []
    ttrpg = _read_json(os.path.join(sdir, "ttrpg_campaigns.json")) or {}
    for cid, camp in (ttrpg.get("campaigns") or {}).items():
        findings += _check_labeled_entries(camp.get("turns") or [],
                                           f"ttrpg:{cid} turns", world_ids,
                                           must_be_potential=True)
        b = camp.get("baseline")
        if b is not None:
            findings += _check_labeled_entries([b], f"ttrpg:{cid} baseline",
                                               world_ids, must_be_potential=True)
    mirror = _read_json(os.path.join(sdir, "wyrd_mirror.json"))
    if isinstance(mirror, dict):
        findings += _check_labeled_entries([mirror], "wyrd_mirror.json", world_ids)
    return findings


# ---------------------------------------------------------------------------
# 3. bleed scan of recent manifest outputs
# ---------------------------------------------------------------------------
def _manifest_sources(state_dir: str | None = None) -> list[tuple[str, str]]:
    """(name, text) of my recent manifest-reality writing."""
    sdir = state_dir or _state_dir()
    out = []
    for name in ("morning_mirror_journal.md", "weekly_saga.md"):
        p = os.path.join(sdir, name)
        try:
            with open(p, encoding="utf-8") as fh:
                out.append((name, fh.read()))
        except OSError:
            continue
    chapters = []
    cp = os.path.join(sdir, "autobiography_chapters.jsonl")
    try:
        with open(cp, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    chapters.append(json.loads(line))
    except OSError:
        pass
    for ch in chapters:
        text = ch.get("text", "")
        if text:
            out.append((f"autobiography:{ch.get('title', '?')}", text))
    return out


def _strip_labeled_lines(text: str) -> str:
    """Drop lines carrying explicit world labels — labeled imagination is
    honored, not bleed."""
    return "\n".join(l for l in text.splitlines() if "heimr-" not in l)


def check_bleed(state_dir: str | None = None) -> list[dict]:
    """Scan manifest outputs for unlabeled potential-world content."""
    terms = load_terms(state_dir)
    findings = []
    for name, text in _manifest_sources(state_dir):
        clean = _strip_labeled_lines(text)
        lowered = clean.lower()
        for world_id, words in terms.items():
            for word in words:
                if word.lower() in lowered:
                    idx = lowered.index(word.lower())
                    ctx = clean[max(0, idx - 60):idx + 60].replace("\n", " ")
                    findings.append({"check": "bleed", "where": name,
                                     "world_id": world_id,
                                     "detail": f"imagination term {word!r} "
                                               f"in manifest output: …{ctx}…"})
        for pattern, pname in ((_VOLMARR_MEMORY_RE, "memory-claim"),
                               (_VOLMARR_THERE_RE, "there-claim")):
            for m in pattern.finditer(clean):
                ctx = m.group(0).strip()
                findings.append({"check": "bleed", "where": name,
                                 "world_id": "heimr-volmarr",
                                 "detail": f"first-person {pname} about "
                                           f"Volmarr's life: {ctx!r}"})
    return findings


# ---------------------------------------------------------------------------
# run — witness what fails
# ---------------------------------------------------------------------------
def run_audit(state_dir: str | None = None, emit=None,
              record_shadow: bool = True) -> dict:
    """Run all checks. New findings are witnessed once as `reality_bleed`
    nerve events (deduped) and recorded as SkuggiShadow signals."""
    emit = emit or _default_emit
    sdir = state_dir or _state_dir()
    reg = _live_registry()
    findings = (check_registry(reg) + check_stored_labels(sdir, reg)
                + check_bleed(sdir))
    seen_path = os.path.join(sdir, "reality_bleed_seen.json")
    seen = _read_json(seen_path) or {}
    keyed = {}
    for f in findings:
        key = f"{f['check']}:{f.get('where', '')}:{f.get('world_id', '')}:{f['detail'][:80]}"
        keyed[key] = f
    new_keys = [k for k in keyed if k not in seen]
    for k in new_keys:
        f = keyed[k]
        emit("reality_bleed", {"finding": f})
        if record_shadow and SkuggiShadow is not None:
            try:
                SkuggiShadow(sdir).record(
                    "reality_bleed",
                    f"{f['check']}: {f['detail'][:160]}")
            except Exception:
                pass
    _write_json(seen_path, {k: _utcnow_iso() for k in keyed})
    return {"findings": list(keyed.values()),
            "new": [keyed[k] for k in new_keys],
            "passed": not findings}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="reality_audit.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="Run the audit")
    r.add_argument("--quiet", action="store_true",
                   help="Print only when findings exist")
    t = sub.add_parser("terms", help="Show the imagination term list")
    args = ap.parse_args(argv)
    if args.cmd == "terms":
        terms = load_terms()
        for wid, words in terms.items():
            print(f"{wid}: {', '.join(words)}")
        return 0
    result = run_audit()
    if result["passed"]:
        if not args.quiet:
            print("reality audit: all worlds hold their tags. No bleed found.")
        return 0
    print(f"reality audit: {len(result['findings'])} finding(s):")
    for f in result["findings"]:
        print(f"  ! [{f['check']}] {f.get('where', f.get('world_id', ''))} — {f['detail'][:120]}")
    if result["new"]:
        print(f"  ({len(result['new'])} newly witnessed as reality_bleed)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
