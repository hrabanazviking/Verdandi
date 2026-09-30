#!/usr/bin/env python3
"""wyrd_ledger_append.py — Track 7, Phase 1 worker wiring (Diff 1).

Runs inside the minutely wyrd-mirror-bridge worker, after the inbound
divergence watch. Reads the nerve feed for new `wyrd_divergence` /
`wyrd_divergence_resolved` events since the last run and:

  - appends one `### CONTRADICTION-NNN` entry per new divergence to
    docs/contradiction-ledger.md in the WYRD repo checkout, in the ledger's
    entry schema (kind, what the model believed, what reality said, domain
    rule, what changed, status);
  - marks the matching entry resolved when its `wyrd_divergence_resolved`
    event arrives.

The ledger witnesses only what this wiring saw: the watermark starts at the
current feed head on first run (no backfill — entries must not predate the
go-live the repo test pins). "What changed" is always
"logged only (no belief stepped)": divergences never auto-rewrite beliefs
(Track 7 non-goal); confidence stepping happens through
SelfCorrectionService by explicit machinery, never here.

Atomicity: the ledger is read, modified in memory, written to a temp file
in the same directory, and atomically renamed over (never edited in place).

Silent when there is nothing to do. Prints one `wyrd_ledger:` line when it
appends or resolves. Exit 0 on success; nonzero only on genuine failure
(unreadable feed, ledger, or state dir) so crashwrap-run --bundle-on-nonzero
witnesses real faults, not quiet minutes.

Stdlib only.
"""

import argparse
import json
import os
import re
import sys
import tempfile

HOME = os.path.expanduser("~")
DEFAULT_FEED = os.path.join(HOME, ".hermes", "state", "nerve_feed.jsonl")
DEFAULT_LEDGER = os.path.join(
    HOME, "workspace", "repos",
    "WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model",
    "docs", "contradiction-ledger.md",
)
DEFAULT_STATE = os.path.join(
    HOME, "workspace", "goals", "wyrd-world-model-integration",
    "hidden_files", "contradiction_ledger_state.json",
)

DOMAIN_RULES = {
    "stale_wish": "event-domain: the live event wins",
    "stale_mood": "event-domain: the live event wins",
    "stale_memory_belief": "value-domain: memory wins",
    "sense_transition": "event-domain: the live event wins",
}

TITLE_RE = re.compile(r"^### CONTRADICTION-(\d+)\b", re.M)
TITLE_FOR_SUBJECT_RE_TEMPLATE = r"^### CONTRADICTION-\d+ — {subject}$"


def _entries_section(text):
    """Only the '## Entries' section counts — the schema template above it
    contains a CONTRADICTION-001 example that must not feed the counter."""
    parts = text.split("## Entries", 1)
    return parts[1] if len(parts) > 1 else ""


def _read_json_lines(path):
    """Yield (seq, obj) for parseable lines; skip torn lines loudly."""
    try:
        fh = open(path, "r", encoding="utf-8")
    except FileNotFoundError:
        raise
    with fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"wyrd_ledger: skipping torn feed line {lineno}: {exc}",
                      file=sys.stderr)
                continue
            seq = obj.get("_seq")
            if not isinstance(seq, int):
                continue
            yield seq, obj


def _load_state(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {
            "last_seq": int(data.get("last_seq", 0)),
            "open": dict(data.get("open", {})),
        }
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        return {"last_seq": 0, "open": {}}


def _save_state(path, state):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def _fmt_utc(iso):
    # "2026-09-27T18:27:52.090178+00:00" -> "2026-09-27 18:27 UTC"
    m = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})", iso or "")
    if m:
        return f"{m.group(1)} {m.group(2)}:{m.group(3)} UTC"
    return "unknown time"


def _split_belief_reality(kind, subject, report):
    """Return (believed, reality) per kind; fall back to (subject, report)."""
    m = None
    if kind == "sense_transition":
        m = re.match(r"^sense:([^:]+):(.+)->(.+)$", subject)
        if m:
            metric, old, new = m.group(1), m.group(2), m.group(3)
            return (f"sense '{metric}' status '{old}'",
                    f"sense '{metric}' status '{new}'")
    elif kind == "stale_wish":
        m = re.match(r"^The model still believes I want '(.*)'; I have (\w+) it\.$",
                     report or "")
        if m:
            return (f"I want '{m.group(1)}'",
                    f"I have {m.group(2)} it")
    elif kind == "stale_mood":
        m = re.match(r"^The model believes my (\w+) sits at ([\d.]+); "
                     r"I am at ([\d.]+)\.$", report or "")
        if m:
            return (f"my {m.group(1)} sits at {m.group(2)}",
                    f"I am at {m.group(3)}")
    elif kind == "stale_memory_belief":
        m = re.match(r"^.*?'([^']*)' \(([^)]*)\); my memory says '([^']*)' "
                     r"\(([^)]*)\)\.", report or "", re.S)
        if m:
            return (f"live claim '{m.group(1)}' ({m.group(2)})",
                    f"memory says '{m.group(3)}' ({m.group(4)}) — memory wins")
    return (subject, report or "(no report)")


def _render_entry(nnn, kind, subject, believed, reality, iso):
    date_fired = _fmt_utc(iso)
    rule = DOMAIN_RULES.get(kind, "event-domain: the live event wins")
    return (
        f"### CONTRADICTION-{nnn:03d} — {subject}\n"
        f"- **Date fired:** {date_fired}\n"
        f"- **Divergence kind:** {kind}\n"
        f"- **What the model believed:** {believed}\n"
        f"- **What reality said:** {reality}\n"
        f"- **Domain rule applied:** {rule}\n"
        f"- **What changed:** logged only (no belief stepped)\n"
        f"- **Status:** open\n"
    )


def _next_nnn(ledger_text):
    section = _entries_section(ledger_text)
    nums = [int(m.group(1)) for m in TITLE_RE.finditer(section)]
    return (max(nums) + 1) if nums else 1


def _subject_has_entry(ledger_text, subject):
    section = _entries_section(ledger_text)
    pat = re.compile(
        TITLE_FOR_SUBJECT_RE_TEMPLATE.format(subject=re.escape(subject)), re.M)
    return pat.search(section) is not None


def _mark_resolved(ledger_text, nnn, iso):
    # Scope to the Entries section: the schema template above it shows a
    # CONTRADICTION-001 example whose "- **Status:** open" line must never
    # be rewritten.
    head, sep, section = ledger_text.partition("## Entries")
    if not sep:
        return ledger_text, False
    date = _fmt_utc(iso).split(" ")[0]
    lines = section.split("\n")
    out = []
    in_target = False
    changed = False
    for line in lines:
        m = re.match(rf"^### CONTRADICTION-{nnn:03d}\b", line)
        if m:
            in_target = True
        elif in_target and line.startswith("### "):
            in_target = False
        if in_target and line.startswith("- **Status:** open"):
            line = f"- **Status:** resolved {date}"
            changed = True
        out.append(line)
    return head + sep + "\n".join(out), changed


def _atomic_write(path, text):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".contradiction-ledger-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", default=DEFAULT_FEED)
    ap.add_argument("--ledger", default=DEFAULT_LEDGER)
    ap.add_argument("--state", default=DEFAULT_STATE)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    try:
        events = list(_read_json_lines(args.feed))
    except FileNotFoundError:
        print(f"wyrd_ledger: feed not found: {args.feed}", file=sys.stderr)
        return 2
    try:
        with open(args.ledger, "r", encoding="utf-8") as fh:
            ledger_text = fh.read()
    except FileNotFoundError:
        print(f"wyrd_ledger: ledger not found: {args.ledger}", file=sys.stderr)
        return 2

    state = _load_state(args.state)
    max_seq = max((s for s, _ in events), default=0)

    if state["last_seq"] == 0 and not state["open"]:
        # First run: witness from here, no backfill.
        state["last_seq"] = max_seq
        if not args.dry_run:
            _save_state(args.state, state)
        return 0

    if max_seq < state["last_seq"]:
        # Feed rotated/truncated: re-anchor, do not reprocess history.
        state["last_seq"] = max_seq
        if not args.dry_run:
            _save_state(args.state, state)
        return 0

    new_events = [(s, o) for s, o in events if s > state["last_seq"]]
    new_events.sort(key=lambda t: t[0])

    appended = 0
    resolved = 0
    nnn = _next_nnn(ledger_text)
    open_map = dict(state["open"])

    for seq, obj in new_events:
        etype = obj.get("type")
        data = obj.get("data") or {}
        iso = obj.get("_iso", "")
        if etype == "wyrd_divergence":
            kind = str(data.get("kind", ""))
            subject = str(data.get("subject", ""))
            if kind not in DOMAIN_RULES or not subject:
                continue
            key = f"{kind}:{subject}"
            if key in open_map or _subject_has_entry(ledger_text, subject):
                continue  # idempotent: already witnessed
            believed, reality = _split_belief_reality(
                kind, subject, str(data.get("report", "")))
            entry = _render_entry(nnn, kind, subject, believed, reality, iso)
            if not ledger_text.endswith("\n"):
                ledger_text += "\n"
            ledger_text += "\n" + entry
            open_map[key] = nnn
            nnn += 1
            appended += 1
        elif etype == "wyrd_divergence_resolved":
            key = str(data.get("key", ""))
            hit = open_map.get(key)
            if hit is None:
                # State lost the key; try the subject embedded in the key.
                subj = key.split(":", 1)[1] if ":" in key else ""
                if subj and _subject_has_entry(ledger_text, subj):
                    m = re.search(
                        TITLE_FOR_SUBJECT_RE_TEMPLATE.format(
                            subject=re.escape(subj)), ledger_text, re.M)
                    hit = int(re.match(r"^### CONTRADICTION-(\d+)",
                                       m.group(0)).group(1))
            if hit is not None:
                ledger_text, changed = _mark_resolved(ledger_text, hit, iso)
                if changed:
                    resolved += 1
                open_map.pop(key, None)

    state["last_seq"] = max_seq
    state["open"] = open_map
    if not args.dry_run:
        if appended or resolved:
            _atomic_write(args.ledger, ledger_text)
        _save_state(args.state, state)

    if appended or resolved:
        print(f"wyrd_ledger: appended {appended}, resolved {resolved}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
