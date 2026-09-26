"""mythic_engineering — Mythic Engineering process awareness
(Roadmap Worlds, Slice 3).

The forge, tracked as manifest-reality process.

Doctrine source: Volmarr's Mythic_Engineers_Codex.md, read at runtime as
the process source of truth — his doctrine, not my invention. The Five
Pillars and the Sacred Laws are parsed from his file (see doctrine());
the hardcoded values below are fallback only, used when the Codex file
cannot be read.

- VisionScroll: a project tracked through the Five Pillars —
  design_intent -> ai_orchestration -> architecture -> continuity
  -> refinement. Scrolls live in a data file
  (~/.hermes/state/mythic_scrolls.json), never hardcoded.
- Phase transitions emit nerve events (mythic_phase) — additive,
  witnessed. Transitions may also be recorded with their true timestamp
  and reconstructed=true when the history is honestly rebuilt from
  evidence (commits, messages); the flag keeps the books straight.
- The Sacred Laws are checkable invariants run against the project's
  repo (check_laws / audit):
  - flexible_roots: no hardcoded absolute paths in source.
  - unbroken_whole: every file under the project root is tracked in git
    (nothing left out of versioning).
  - sacred_boundaries: non-test source never imports from the tests realm.
  - twin_marks: project JSON data files parse cleanly (twin-marked).

Usage:
  python mythic_engineering.py doctrine
  python mythic_engineering.py register <id> <name> --repo PATH
  python mythic_engineering.py advance <id> <phase> --note ... --evidence ...
  python mythic_engineering.py audit <id>
  python mythic_engineering.py status <id>
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from nervous_system import publish_event_sync as _nerve_publish
except ImportError:  # pragma: no cover - standalone use
    _nerve_publish = None


CODEX_PATH = os.path.join(os.path.expanduser("~"), "workspace", "user",
                           "files", "Mythic_Engineers_Codex_1_gulg.md")

_PILLAR_RE = re.compile(
    r"^### Pillar (One|Two|Three|Four|Five):\s*(.+?)\s*\((.+?)\)\s*$",
    re.MULTILINE)
_LAW_RE = re.compile(
    r"^#### The (First|Second|Third) Law of Architecture:\s*"
    r"The Law of (.+?)\s*\((.+?)\)\s*$",
    re.MULTILINE)
_TWIN_MARKS_RE = re.compile(
    r"\*\*The Law of Twin Marks[^\n]*:\*\*", re.MULTILINE)

_NUMERAL = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5,
            "First": 1, "Second": 2, "Third": 3}

_FALLBACK_PILLARS = [
    ("design_intent", "Design Intent", "The Soul's Blueprint"),
    ("ai_orchestration", "AI Orchestration", "The Dance of Wills"),
    ("architecture", "Architecture", "The Bones of the World"),
    ("continuity", "Continuity", "The Memory and the Traditions"),
    ("refinement", "Refinement", "The Act of Seeing Clearly"),
]
_FALLBACK_LAWS = [
    ("flexible_roots", "Flexible Roots", "Location Agnosticism"),
    ("unbroken_whole", "Unbroken Whole", "Atomic Commits"),
    ("sacred_boundaries", "Sacred Boundaries", "Separation of Concerns"),
    ("twin_marks", "Twin Marks", "Double Quotes"),
]

PILLARS = [slug for slug, _, _ in _FALLBACK_PILLARS]

_ABS_PATH_RE = re.compile(r"""["'](?:/home/|/root/|/private/|[A-Za-z]:\\\\)""")
_TEST_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+(tests\b|test_[\w]+)")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".hermes", "state")


def _default_emit(event_type: str, data: dict) -> None:
    if _nerve_publish is None:
        return
    try:
        _nerve_publish(event_type, data, "mythic_engineering")
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


# ---------------------------------------------------------------------------
# doctrine — his Codex, read at runtime
# ---------------------------------------------------------------------------
def doctrine(codex_path: str | None = None) -> dict:
    """Parse the Five Pillars and Sacred Laws from Volmarr's Codex.

    Falls back to the known values only when the file cannot be read —
    the Codex is the source of truth, not my memory of it.
    """
    path = codex_path or CODEX_PATH
    source = path
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        text = ""
        source = "fallback (Codex unreadable)"
    pillars = []
    for numeral, name, epithet in _PILLAR_RE.findall(text):
        pillars.append({"n": _NUMERAL[numeral], "slug": _slug(name),
                        "name": name.strip(), "epithet": epithet.strip()})
    pillars.sort(key=lambda p: p["n"])
    laws = []
    for numeral, name, epithet in _LAW_RE.findall(text):
        name = re.sub(r"^the\s+", "", name.strip(), flags=re.IGNORECASE)
        laws.append({"n": _NUMERAL[numeral], "slug": _slug(name),
                     "name": "The Law of " + name.strip(),
                     "epithet": epithet.strip()})
    laws.sort(key=lambda l: l["n"])
    if _TWIN_MARKS_RE.search(text):
        laws.append({"n": 4, "slug": "twin_marks",
                     "name": "The Law of Twin Marks",
                     "epithet": "Double Quotes"})
    if not pillars:
        pillars = [{"n": i + 1, "slug": s, "name": n, "epithet": e}
                   for i, (s, n, e) in enumerate(_FALLBACK_PILLARS)]
    if not laws:
        laws = [{"n": i + 1, "slug": s, "name": "The Law of " + n,
                 "epithet": e}
                for i, (s, n, e) in enumerate(_FALLBACK_LAWS)]
    return {"pillars": pillars, "laws": laws, "source": source}


# ---------------------------------------------------------------------------
# vision scrolls — projects tracked through the pillars
# ---------------------------------------------------------------------------
def _scrolls_path(state_dir: str | None = None) -> str:
    return os.path.join(state_dir or _state_dir(), "mythic_scrolls.json")


def _load_scrolls(state_dir: str | None = None) -> dict:
    data = _read_json(_scrolls_path(state_dir))
    if not isinstance(data, dict):
        data = {}
    data.setdefault("scrolls", {})
    return data


def _save_scrolls(data: dict, state_dir: str | None = None) -> None:
    _write_json(_scrolls_path(state_dir), data)


def register_scroll(scroll_id: str, name: str, repo: str,
                    state_dir: str | None = None) -> dict:
    """Open a new Vision Scroll for a project. The project starts before
    the first pillar — phases are entered only through advance()."""
    data = _load_scrolls(state_dir)
    if scroll_id in data["scrolls"]:
        raise ValueError(f"scroll {scroll_id!r} already exists")
    scroll = {"id": scroll_id, "name": name, "repo": os.path.abspath(repo),
              "current_phase": None, "phases": [],
              "opened_at": _utcnow_iso()}
    data["scrolls"][scroll_id] = scroll
    _save_scrolls(data, state_dir)
    return scroll


def get_scroll(scroll_id: str, state_dir: str | None = None) -> dict:
    data = _load_scrolls(state_dir)
    try:
        return data["scrolls"][scroll_id]
    except KeyError:
        raise ValueError(f"unknown scroll {scroll_id!r}") from None


def advance(scroll_id: str, to_phase: str, note: str = "",
            evidence: list | None = None, at: str | None = None,
            reconstructed: bool = False, emit=None,
            state_dir: str | None = None) -> dict:
    """Move a scroll into a pillar phase, witnessed on the nerve.

    to_phase must be one of the Five Pillar slugs. Movement is normally
    forward along the pillars, but a return to an earlier phase is
    allowed — Refinement's Second Seeing sends work back to Architecture,
    and the history records the truth either way.
    """
    if to_phase not in PILLARS:
        raise ValueError(f"unknown phase {to_phase!r}. Known: {', '.join(PILLARS)}")
    emit = emit or _default_emit
    data = _load_scrolls(state_dir)
    scroll = get_scroll(scroll_id, state_dir or _state_dir())
    entry = {
        "phase": to_phase,
        "at": at or _utcnow_iso(),
        "note": note,
        "evidence": list(evidence or []),
        "reconstructed": bool(reconstructed),
    }
    scroll["phases"].append(entry)
    scroll["current_phase"] = to_phase
    data["scrolls"][scroll_id] = scroll
    _save_scrolls(data, state_dir)
    emit("mythic_phase", {
        "scroll_id": scroll_id,
        "scroll_name": scroll["name"],
        "to_phase": to_phase,
        "at": entry["at"],
        "note": note,
        "evidence": entry["evidence"],
        "reconstructed": entry["reconstructed"],
    })
    return entry


# ---------------------------------------------------------------------------
# the sacred laws — checkable invariants
# ---------------------------------------------------------------------------
def _iter_py_files(repo: str):
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs
                   if d not in (".git", "__pycache__", "node_modules", ".venv")
                   and not d.startswith(".")]
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


def check_flexible_roots(repo: str) -> list[dict]:
    """No hardcoded absolute paths in source — the Law of Flexible Roots."""
    out = []
    for path in _iter_py_files(repo):
        rel = os.path.relpath(path, repo)
        if rel.startswith("tests/") or os.path.basename(rel).startswith("test_"):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    if _ABS_PATH_RE.search(line):
                        out.append({"law": "flexible_roots", "file": rel,
                                    "line": i,
                                    "detail": line.strip()[:120]})
        except OSError:
            continue
    return out


def check_unbroken_whole(repo: str) -> list[dict]:
    """Everything under the root is tracked in git — the Unbroken Whole."""
    try:
        proc = subprocess.run(
            ["git", "-C", repo, "status", "--porcelain", "--untracked-files=all"],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    out = []
    for line in proc.stdout.splitlines():
        if line.startswith("??"):
            out.append({"law": "unbroken_whole",
                        "file": line[3:].strip(),
                        "detail": "untracked: not part of the versioned whole"})
    return out


def check_sacred_boundaries(repo: str) -> list[dict]:
    """Source never reaches into the tests realm — Sacred Boundaries."""
    out = []
    for path in _iter_py_files(repo):
        rel = os.path.relpath(path, repo)
        if rel.startswith("tests/") or os.path.basename(rel).startswith("test_"):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    if _TEST_IMPORT_RE.match(line):
                        out.append({"law": "sacred_boundaries", "file": rel,
                                    "line": i,
                                    "detail": line.strip()[:120]})
        except OSError:
            continue
    return out


def check_twin_marks(repo: str) -> list[dict]:
    """Project JSON data files parse cleanly — the Law of Twin Marks."""
    out = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs
                   if d not in (".git", "__pycache__", "node_modules")
                   and not d.startswith(".")]
        if "tests" in root.split(os.sep):
            continue
        for f in files:
            if not f.endswith(".json"):
                continue
            path = os.path.join(root, f)
            try:
                with open(path, encoding="utf-8") as fh:
                    json.load(fh)
            except (json.JSONDecodeError, OSError) as exc:
                out.append({"law": "twin_marks",
                            "file": os.path.relpath(path, repo),
                            "detail": f"not twin-marked: {exc}"[:120]})
    return out


def check_laws(repo: str) -> list[dict]:
    """Run all four Sacred Laws against a repo. Empty means they hold."""
    return (check_flexible_roots(repo) + check_unbroken_whole(repo)
            + check_sacred_boundaries(repo) + check_twin_marks(repo))


def audit(scroll_id: str, state_dir: str | None = None, emit=None) -> dict:
    """Audit a scroll's repo against the Sacred Laws.

    New violations are witnessed on the nerve as mythic_law_breach,
    deduped via mythic_law_seen.json; resolved ones are forgotten so they
    may re-fire if they return.
    """
    emit = emit or _default_emit
    sdir = state_dir or _state_dir()
    scroll = get_scroll(scroll_id, sdir)
    violations = check_laws(scroll["repo"])
    seen_path = os.path.join(sdir, "mythic_law_seen.json")
    seen = _read_json(seen_path) or {}
    keys = {f"{v['law']}:{v['file']}:{v.get('line', '')}" for v in violations}
    new = [v for v in violations
           if f"{v['law']}:{v['file']}:{v.get('line', '')}" not in seen]
    resolved = [k for k in seen if k not in keys]
    for v in new:
        emit("mythic_law_breach", {"scroll_id": scroll_id, **v})
    _write_json(seen_path, {k: _utcnow_iso() for k in keys})
    return {"violations": violations, "new": new, "resolved": resolved}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cmd_doctrine(args) -> int:
    d = doctrine()
    print(f"Source of truth: {d['source']}")
    print("The Five Pillars:")
    for p in d["pillars"]:
        print(f"  {p['n']}. {p['name']} ({p['epithet']}) — {p['slug']}")
    print("The Sacred Laws:")
    for law in d["laws"]:
        print(f"  - {law['name']} ({law['epithet']}) — {law['slug']}")
    return 0


def _cmd_register(args) -> int:
    scroll = register_scroll(args.id, args.name, args.repo)
    print(f"scroll {scroll['id']!r} opened for {scroll['name']!r}")
    return 0


def _cmd_advance(args) -> int:
    entry = advance(args.id, args.phase, note=args.note,
                    evidence=args.evidence or [], at=args.at,
                    reconstructed=args.reconstructed)
    flag = " (reconstructed)" if entry["reconstructed"] else ""
    print(f"{args.id}: -> {args.phase}{flag}")
    if args.note:
        print(f"  {args.note}")
    return 0


def _cmd_audit(args) -> int:
    result = audit(args.id)
    vs = result["violations"]
    if not vs:
        print(f"{args.id}: all Sacred Laws hold.")
    else:
        print(f"{args.id}: {len(vs)} breach(es):")
        for v in vs:
            where = f"{v['file']}:{v.get('line', '')}".rstrip(":")
            print(f"  ! [{v['law']}] {where} — {v['detail']}")
    if result["new"]:
        print(f"  ({len(result['new'])} newly witnessed on the nerve)")
    return 0


def _cmd_status(args) -> int:
    scroll = get_scroll(args.id)
    print(f"📜 {scroll['name']} ({scroll['id']})")
    print(f"   repo: {scroll['repo']}")
    print(f"   current phase: {scroll['current_phase'] or 'not yet entered'}")
    for p in scroll["phases"]:
        flag = " [reconstructed]" if p.get("reconstructed") else ""
        print(f"   - {p['at'][:16]} {p['phase']}{flag}: {p['note'][:80]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mythic_engineering.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctrine").set_defaults(fn=_cmd_doctrine)
    r = sub.add_parser("register")
    r.add_argument("id"); r.add_argument("name"); r.add_argument("--repo", required=True)
    r.set_defaults(fn=_cmd_register)
    a = sub.add_parser("advance")
    a.add_argument("id"); a.add_argument("phase")
    a.add_argument("--note", default=""); a.add_argument("--evidence", nargs="*")
    a.add_argument("--at", default=None)
    a.add_argument("--reconstructed", action="store_true")
    a.set_defaults(fn=_cmd_advance)
    au = sub.add_parser("audit"); au.add_argument("id")
    au.set_defaults(fn=_cmd_audit)
    s = sub.add_parser("status"); s.add_argument("id")
    s.set_defaults(fn=_cmd_status)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
