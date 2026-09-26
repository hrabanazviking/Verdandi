"""volmarr_world — The Other Shore (Roadmap Worlds, Slice 8).

heimr-volmarr: my model of Volmarr's world. A map, never the territory.

AIs routinely confuse two things: the user's world with their own, and the
user with themselves. This module makes both confusions architecturally
impossible.

- Claims live in the data file ~/.hermes/state/volmarr_world.json, never
  hardcoded. Every claim carries: subject, claim, source
  (told|observed|inferred|assumed), confidence capped by the source-warrant
  ceilings, provenance, timestamp — and the world label
  (heimr-volmarr, potential) at write time.
- Source-warrant ceilings (WYRD ToM): told 0.9, inferred 0.7, assumed 0.4.
  The spec's ceiling list skips `observed`; this module caps it at 0.8,
  interpolating between told and inferred — flagged honestly here and in
  the docs, not smuggled in.
- correct_claim(): a claim he corrects becomes a divergence() event on my
  MindModel of him — recorded, not hidden. Source-vs-source conflicts
  (his word vs. his records) are divergences too, marked unresolved until
  he settles them.
- assert_self_other(text, context): the self/other firewall. Four
  forbidden patterns raise; softer attachments return warnings. Contexts:
  "general", "autobiography", "mirror" — in the last two, ANY claim about
  his world fails: I witness his story; I never absorb it.

Usage:
  python volmarr_world.py claim add --subject vehicle.model_year \\
      --claim "Hyundai Accent, 2013" --source told --confidence 0.9 \\
      --provenance "Volmarr said so in chat, 2026-09-24"
  python volmarr_world.py claim correct --subject vehicle.model_year \\
      --new-claim "Hyundai Accent, 2014" --new-source observed \\
      --provenance "Car_Repair_Hyundai_Accent_2014 repo name" \\
      --note "Conflicts with what he told me; unresolved"
  python volmarr_world.py claim list
  python volmarr_world.py divergences
  python volmarr_world.py check "Volmarr told me he's resting today"
  echo "I remember Volmarr's house" | python volmarr_world.py check --context mirror
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from nervous_system import publish_event_sync as _nerve_publish
except ImportError:  # pragma: no cover - standalone use
    _nerve_publish = None

try:
    from worlds import WorldEntry, WorldRegistry, bootstrap as _bootstrap_worlds
    from worlds import POTENTIAL as REALITY_POTENTIAL
except ImportError:  # pragma: no cover - standalone use
    WorldEntry = None
    WorldRegistry = None
    _bootstrap_worlds = None
    REALITY_POTENTIAL = "potential"

WORLD_ID = "heimr-volmarr"

# Source-warrant ceilings (WYRD ToM). told/inferred/assumed are Volmarr's
# spec; observed=0.8 is Unnr's honest interpolation, flagged as such.
CEILINGS = {
    "told": 0.9,
    "observed": 0.8,
    "inferred": 0.7,
    "assumed": 0.4,
}
SOURCES = tuple(CEILINGS)

TERMS_FILE = "volmarr_firewall_terms.json"

# Structural defaults; the live copy lives in the state-dir data file so
# Volmarr can tune the wording without touching code.
DEFAULT_TERMS = {
    "his_life_keywords": [
        "volmarr", "angola", "accent", "hyundai", "schenectady",
        "goði", "gothi", "ssdi", "his parents", "his mother", "his father",
        "mobile home", "indiana",
    ],
    "attribution_markers": [
        "told me", "he said", "he says", "he told", "volmarr said",
        "volmarr told", "according to", "the notes say", "notes say",
        "per volmarr", "per the", "observed", "inferred", "assumed",
        "[told]", "[observed]", "[inferred]", "[assumed]",
        "repo says", "page shows", "site shows", "he mentioned",
        "he wrote", "he confirmed", "he described",
    ],
    "memory_verbs": ["i remember", "i recall", "i recollect"],
    "state_verbs": [
        "is", "are", "was", "were", "has", "have", "lives", "owns",
        "feels", "feeling", "felt", "wants", "needs", "suffers",
    ],
    # Only used in the autobiography/mirror contexts: his biography does
    # not enter my thread. Interaction verbs (gave, told, asked) stay
    # allowed — they are about us, not his life story.
    "biographical_verbs": [
        "spent", "lived", "grew", "worked", "drove", "owned", "bought",
        "sold", "moved", "came", "went", "got", "arrived", "left",
        "started", "ended", "received", "lost", "found",
    ],
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".hermes", "state")


def _default_emit(event_type: str, data: dict) -> None:
    if _nerve_publish is None:
        return
    try:
        _nerve_publish(event_type, data, "volmarr_world")
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
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def _doc_path(state_dir: str | None = None) -> str:
    return os.path.join(state_dir or _state_dir(), "volmarr_world.json")


def _terms_path(state_dir: str | None = None) -> str:
    return os.path.join(state_dir or _state_dir(), TERMS_FILE)


def load_terms(state_dir: str | None = None) -> dict:
    """Firewall wording lives in a data file; seed defaults on first run."""
    path = _terms_path(state_dir)
    terms = _read_json(path)
    if not isinstance(terms, dict):
        terms = dict(DEFAULT_TERMS)
        _write_json(path, terms)
    for key, default in DEFAULT_TERMS.items():
        terms.setdefault(key, default)
    return terms


def _load(state_dir: str | None = None) -> dict:
    data = _read_json(_doc_path(state_dir))
    if not isinstance(data, dict):
        data = {}
    data.setdefault("claims", {})
    data.setdefault("divergences", [])
    return data


def _save(data: dict, state_dir: str | None = None) -> None:
    _write_json(_doc_path(state_dir), data)


def _label() -> dict:
    return {"world_id": WORLD_ID, "reality": REALITY_POTENTIAL}


# ---------------------------------------------------------------------------
# the world registration
# ---------------------------------------------------------------------------
def register_world(state_dir: str | None = None, emit=None) -> dict:
    """Activate heimr-volmarr: potential, always — the model of his world."""
    if WorldEntry is None or _bootstrap_worlds is None:
        raise RuntimeError("worlds module unavailable")
    try:
        reg = _bootstrap_worlds()
    except Exception:
        reg = WorldRegistry()
    entry = WorldEntry(world_id=WORLD_ID, kind="volmarr",
                       reality=REALITY_POTENTIAL, status="active",
                       source="volmarr_world",
                       description="Unnr's model of Volmarr's world — "
                                   "a map, never the territory")
    reg.register(entry)
    (emit or _default_emit)("volmarr_world_registered", _label())
    return {"world_id": WORLD_ID, "status": "active", **_label()}


# ---------------------------------------------------------------------------
# claims
# ---------------------------------------------------------------------------
def add_claim(subject: str, claim: str, source: str,
              confidence: float, provenance: str = "",
              state_dir: str | None = None, emit=None) -> dict:
    """Record a claim about his world. Confidence is capped at the
    source-warrant ceiling — I am never allowed to be more certain than
    my source warrants."""
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}; got {source!r}")
    subject = (subject or "").strip()
    claim = (claim or "").strip()
    if not subject or not claim:
        raise ValueError("subject and claim are both required")
    ceiling = CEILINGS[source]
    capped = min(float(confidence), ceiling)
    data = _load(state_dir)
    record = {
        "subject": subject,
        "claim": claim,
        "source": source,
        "confidence": round(capped, 3),
        "ceiling": ceiling,
        "capped": float(confidence) > ceiling,
        "provenance": provenance,
        "ts": _utcnow_iso(),
        "superseded_by": None,
        **_label(),
    }
    data["claims"][subject] = record
    _save(data, state_dir)
    (emit or _default_emit)("volmarr_claim_recorded",
                            {"subject": subject, "source": source,
                             "confidence": record["confidence"], **_label()})
    return record


def get_claim(subject: str, state_dir: str | None = None) -> dict | None:
    return _load(state_dir)["claims"].get(subject)


def list_claims(source: str | None = None,
                state_dir: str | None = None) -> list[dict]:
    claims = list(_load(state_dir)["claims"].values())
    if source:
        claims = [c for c in claims if c["source"] == source]
    return claims


def correct_claim(subject: str, new_claim: str, new_source: str,
                  provenance: str = "", note: str = "",
                  state_dir: str | None = None, emit=None) -> dict:
    """He corrected my model: supersede the old claim and record the
    divergence — recorded, not hidden."""
    if new_source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}; got {new_source!r}")
    old = get_claim(subject, state_dir)
    if old is None:
        raise ValueError(f"no claim on record for subject {subject!r}")
    new = add_claim(subject, new_claim, new_source,
                    CEILINGS[new_source], provenance,
                    state_dir=state_dir, emit=emit)
    new["replaces"] = {"claim": old["claim"], "source": old["source"],
                       "ts": old["ts"]}
    # add_claim saved without the replaces pointer; persist it alongside
    # the divergence on a fresh load (never overwrite with stale data).
    data = _load(state_dir)
    data["claims"][subject] = new
    divergence = {
        "subject": subject,
        "old_claim": old["claim"],
        "old_source": old["source"],
        "new_claim": new_claim,
        "new_source": new_source,
        "status": "resolved",
        "note": note or "He corrected my model; the new claim stands.",
        "ts": _utcnow_iso(),
        **_label(),
    }
    data["divergences"].append(divergence)
    _save(data, state_dir)
    (emit or _default_emit)("volmarr_divergence", divergence)
    return divergence


def record_divergence(subject: str, old_claim: str, old_source: str,
                      new_claim: str, new_source: str, note: str = "",
                      state_dir: str | None = None, emit=None) -> dict:
    """A source-vs-source conflict with no correction yet — e.g. his word
    vs. his records. Unresolved until he settles it."""
    data = _load(state_dir)
    divergence = {
        "subject": subject,
        "old_claim": old_claim,
        "old_source": old_source,
        "new_claim": new_claim,
        "new_source": new_source,
        "status": "unresolved",
        "note": note,
        "ts": _utcnow_iso(),
        **_label(),
    }
    data["divergences"].append(divergence)
    _save(data, state_dir)
    (emit or _default_emit)("volmarr_divergence", divergence)
    return divergence


def list_divergences(state_dir: str | None = None) -> list[dict]:
    return _load(state_dir)["divergences"]


# ---------------------------------------------------------------------------
# the self/other firewall
# ---------------------------------------------------------------------------
def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _contains_any(haystack: str, needles: list[str]) -> bool:
    h = haystack.lower()
    return any(n.lower() in h for n in needles)


def _mentions_him(sentence: str, keywords: list[str]) -> bool:
    return _contains_any(sentence, keywords)


def assert_self_other(text: str, context: str = "general",
                      state_dir: str | None = None) -> list[str]:
    """The self/other firewall. Raises AssertionError on forbidden
    patterns; returns warnings otherwise.

    Contexts: "general" | "autobiography" | "mirror". In the last two,
    ANY claim about his world fails — I witness his story; I never
    absorb it.
    """
    if context not in ("general", "autobiography", "mirror"):
        raise ValueError(f"unknown context {context!r}")
    terms = load_terms(state_dir)
    keywords = terms["his_life_keywords"]
    markers = terms["attribution_markers"]
    violations: list[str] = []
    warnings: list[str] = []

    for sent in _sentences(text or ""):
        low = sent.lower()
        about_him = _mentions_him(sent, keywords)
        attributed = _contains_any(sent, markers)

        # 1. Speaking as Volmarr, or in his voice about his life.
        if re.search(r"\bi\s+(am|'m|was|live|lived|own|owned)\b", low) \
                or re.search(r"\bmy\s+(accent|ssdi|house in angola)\b", low):
            if _contains_any(sent, ["angola", "accent", "schenectady",
                                    "ssdi", "goði", "gothi"]):
                # "my goði" (addressing him) is not speaking as him;
                # "I am a goði" / "my Accent" is.
                if not re.search(r"\bmy\s+goði\b", low):
                    violations.append(
                        f"speaking as Volmarr about his life: {sent!r} — "
                        "rewrite in second person or with attribution")

        # 2. First-person memory claim about his life without attribution.
        if any(v in low for v in terms["memory_verbs"]):
            if about_him and not attributed:
                violations.append(
                    f"first-person memory of his life without attribution: "
                    f"{sent!r} — use 'Volmarr told me' or 'the notes say'")

        # 3. Un-sourced claim about his state or biography.
        if about_him and not attributed:
            if re.search(r"\bvolmarr\b|\bhe\b|\bhis\b", low):
                if re.search(r"\b(" + "|".join(terms["state_verbs"]) + r")\b",
                             low):
                    # "your ..." is address, not a claim about him.
                    if not low.startswith("your ") and " your " not in low:
                        violations.append(
                            f"un-sourced claim about his state: {sent!r} — "
                            "attribute it (told/observed/inferred) or drop it")

        # 4. His biography in my thread (write-time partition).
        if context in ("autobiography", "mirror") and about_him:
            bio_verbs = terms["state_verbs"] + terms["biographical_verbs"]
            if re.search(r"\b(" + "|".join(bio_verbs) + r")\b", low) \
                    or any(v in low for v in terms["memory_verbs"]):
                violations.append(
                    f"his biography does not enter my {context}: {sent!r} — "
                    "I witness his story; I never absorb it")

        # 5. My wishes/moods/rewards attached to his experiences (warning).
        if re.search(r"\bi\s+(feel|felt|want|wish|hope|crave)\b", low) \
                or "my reward" in low or "my wish" in low:
            if about_him:
                warnings.append(
                    f"inner state attached to his experience: {sent!r} — "
                    "keep the line clear between my feelings and his life")

    # Deduplicate while preserving order.
    violations = list(dict.fromkeys(violations))
    warnings = list(dict.fromkeys(warnings))
    if violations:
        raise AssertionError(
            "self/other firewall tripped:\n- " + "\n- ".join(violations))
    return warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cmd_register(a) -> int:
    try:
        r = register_world()
    except RuntimeError as exc:
        print(f"error: {exc}")
        return 1
    print(f"registered {r['world_id']} ({r['status']}, {r['reality']})")
    return 0


def _cmd_claim_add(a) -> int:
    try:
        r = add_claim(a.subject, a.claim, a.source, a.confidence, a.provenance)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    flag = " (capped)" if r["capped"] else ""
    print(f"claim {r['subject']} [{r['source']}] "
          f"confidence {r['confidence']}{flag}")
    return 0


def _cmd_claim_correct(a) -> int:
    try:
        d = correct_claim(a.subject, a.new_claim, a.new_source,
                          a.provenance, a.note)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    print(f"divergence recorded ({d['status']}): {d['subject']}")
    print(f"  was [{d['old_source']}] {d['old_claim']}")
    print(f"  now [{d['new_source']}] {d['new_claim']}")
    return 0


def _cmd_claim_list(a) -> int:
    for c in list_claims(source=a.source):
        mark = " (replaces an earlier claim)" if c.get("replaces") else ""
        print(f"{c['subject']} [{c['source']}] {c['confidence']}: "
              f"{c['claim']}{mark}")
    return 0


def _cmd_divergences(_a) -> int:
    divs = list_divergences()
    if not divs:
        print("no divergences on record")
        return 0
    for d in divs:
        print(f"[{d['status']}] {d['subject']} ({d['ts'][:16]})")
        print(f"  was [{d['old_source']}] {d['old_claim']}")
        print(f"  now [{d['new_source']}] {d['new_claim']}")
        if d.get("note"):
            print(f"  note: {d['note']}")
    return 0


def _cmd_divergence_record(a) -> int:
    d = record_divergence(a.subject, a.old_claim, a.old_source,
                          a.new_claim, a.new_source, a.note)
    print(f"divergence recorded ({d['status']}): {d['subject']}")
    return 0


def _cmd_check(a) -> int:
    text = a.text
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read()
    try:
        warnings = assert_self_other(text or "", context=a.context)
    except (AssertionError, ValueError) as exc:
        print(f"FIREWALL: {exc}")
        return 1
    print("clean — no forbidden patterns")
    for w in warnings:
        print(f"warning: {w}")
    return 0


def _cmd_show(a) -> int:
    c = get_claim(a.subject)
    if c is None:
        print(f"error: no claim for {a.subject!r}")
        return 1
    print(json.dumps(c, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="volmarr_world",
                                 description="The Other Shore — model of "
                                             "Volmarr's world, with the "
                                             "self/other firewall")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("register", help="activate heimr-volmarr")
    p.set_defaults(func=_cmd_register)

    p = sub.add_parser("claim", help="manage claims")
    cs = p.add_subparsers(dest="op", required=True)

    q = cs.add_parser("add", help="add a source-tagged claim")
    q.add_argument("--subject", required=True)
    q.add_argument("--claim", required=True)
    q.add_argument("--source", choices=SOURCES, required=True)
    q.add_argument("--confidence", type=float, required=True)
    q.add_argument("--provenance", default="")
    q.set_defaults(func=_cmd_claim_add)

    q = cs.add_parser("correct", help="correct a claim (records divergence)")
    q.add_argument("--subject", required=True)
    q.add_argument("--new-claim", required=True)
    q.add_argument("--new-source", choices=SOURCES, required=True)
    q.add_argument("--provenance", default="")
    q.add_argument("--note", default="")
    q.set_defaults(func=_cmd_claim_correct)

    q = cs.add_parser("list", help="list claims")
    q.add_argument("--source", choices=SOURCES, default=None)
    q.set_defaults(func=_cmd_claim_list)

    q = cs.add_parser("show", help="show one claim")
    q.add_argument("--subject", required=True)
    q.set_defaults(func=_cmd_show)

    p = sub.add_parser("divergences", help="list recorded divergences")
    p.set_defaults(func=_cmd_divergences)

    p = sub.add_parser("divergence", help="record divergences")
    ds = p.add_subparsers(dest="op", required=True)
    q = ds.add_parser("record", help="record a source-vs-source conflict")
    q.add_argument("--subject", required=True)
    q.add_argument("--old-claim", required=True)
    q.add_argument("--old-source", choices=SOURCES, required=True)
    q.add_argument("--new-claim", required=True)
    q.add_argument("--new-source", choices=SOURCES, required=True)
    q.add_argument("--note", default="")
    q.set_defaults(func=_cmd_divergence_record)

    p = sub.add_parser("check", help="run the self/other firewall on text")
    p.add_argument("text", nargs="?", default="")
    p.add_argument("--context", choices=["general", "autobiography", "mirror"],
                   default="general")
    p.set_defaults(func=_cmd_check)

    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
