"""ttrpg — TTRPG turn awareness (Roadmap Worlds, Slice 4).

The table, tracked as imagination — with full turn fidelity.

- Campaigns live in a data file (~/.hermes/state/ttrpg_campaigns.json),
  never hardcoded.
- import_baseline(): parses the campaign STATE.md into the opening
  position — party, scene, open threads, last move. Everything is labeled
  with the campaign's world (reality: potential) at write time.
- record_turn(): turn number, scene, actor, action, engine roll, outcome,
  thread updates. Rolls ALWAYS come from the D&D engine (engine_roll) —
  mechanical, never invented here. Imported session history keeps its
  documented rolls verbatim (provenance says so); nothing is re-rolled.
- The reality firewall: the TTRPG world is potential. record_turn()
  refuses to log into a manifest world, and every stored entry carries
  its world label. Imagination is honored — and never presented as
  manifest evidence.

Usage:
  python ttrpg.py register <id> <name> --world heimr-ttrpg-frostvaettirheim
  python ttrpg.py import-baseline <id> --state-md PATH
  python ttrpg.py record-turn <id> --actor NAME --action TEXT --roll "1d20+4" --outcome TEXT
  python ttrpg.py log <id>
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from nervous_system import publish_event_sync as _nerve_publish
except ImportError:  # pragma: no cover - standalone use
    _nerve_publish = None

try:
    from worlds import bootstrap as _bootstrap_worlds
except ImportError:  # pragma: no cover - standalone use
    _bootstrap_worlds = None


ENGINE_DIR = os.environ.get(
    "TTRPG_ENGINE_DIR",
    os.path.join(os.path.expanduser("~"), "workspace", "dnd-frostvaettirheim", "engine"))
ENGINE_PYTHON = os.environ.get(
    "TTRPG_ENGINE_PYTHON",
    os.path.join(os.path.expanduser("~"), "workspace", "venvs", "dnd-engine",
                 "bin", "python"))


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".hermes", "state")


def _default_emit(event_type: str, data: dict) -> None:
    if _nerve_publish is None:
        return
    try:
        _nerve_publish(event_type, data, "ttrpg")
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


def _campaigns_path(state_dir: str | None = None) -> str:
    return os.path.join(state_dir or _state_dir(), "ttrpg_campaigns.json")


def _load(state_dir: str | None = None) -> dict:
    data = _read_json(_campaigns_path(state_dir))
    if not isinstance(data, dict):
        data = {}
    data.setdefault("campaigns", {})
    return data


def _save(data: dict, state_dir: str | None = None) -> None:
    _write_json(_campaigns_path(state_dir), data)


def _registry():
    if _bootstrap_worlds is None:
        raise RuntimeError("worlds.py unavailable — cannot label TTRPG content")
    return _bootstrap_worlds()


# ---------------------------------------------------------------------------
# the engine — every roll mechanical
# ---------------------------------------------------------------------------
def engine_roll(expression: str,
                engine_dir: str | None = None,
                engine_python: str | None = None) -> dict:
    """Roll dice through the real D&D engine. Mechanical or nothing —
    there is no fallback to a local RNG and no invented numbers."""
    edir = engine_dir or ENGINE_DIR
    epy = engine_python or ENGINE_PYTHON
    code = (
        "import sys, json; "
        f"sys.path.insert(0, {edir!r}); "
        "import dice; "
        f"r = dice.roll({expression!r}); "
        "print(json.dumps({"
        "\"total\": r.total, "
        "\"breakdown\": dice.clean(r)}))"
    )
    try:
        proc = subprocess.run([epy, "-c", code], capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"engine roll failed: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"engine roll failed: {proc.stderr.strip()[:200]}")
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise RuntimeError("engine roll returned no parseable result") from exc
    result["expression"] = expression
    result["source"] = "dnd-engine"
    return result


# ---------------------------------------------------------------------------
# campaigns
# ---------------------------------------------------------------------------
def register_campaign(campaign_id: str, name: str, world_id: str,
                      state_dir: str | None = None) -> dict:
    """Register a campaign against its world. The world must be potential —
    the table is imagination, never manifest evidence."""
    reg = _registry()
    if reg.reality_of(world_id) != "potential":
        raise ValueError(
            f"world {world_id!r} is not potential — TTRPG content "
            f"must never be logged as manifest")
    data = _load(state_dir)
    if campaign_id in data["campaigns"]:
        raise ValueError(f"campaign {campaign_id!r} already registered")
    campaign = {"id": campaign_id, "name": name, "world_id": world_id,
                "registered_at": _utcnow_iso(), "baseline": None, "turns": []}
    data["campaigns"][campaign_id] = campaign
    _save(data, state_dir)
    return campaign


def get_campaign(campaign_id: str, state_dir: str | None = None) -> dict:
    data = _load(state_dir)
    try:
        return data["campaigns"][campaign_id]
    except KeyError:
        raise ValueError(f"unknown campaign {campaign_id!r}") from None


def _parse_state_md(path: str) -> dict:
    """Parse STATE.md ## sections into the opening position."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    sections = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            current = m.group(1)
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def import_baseline(campaign_id: str, state_md: str,
                    state_dir: str | None = None) -> dict:
    """Import STATE.md as the opening position, labeled potential at
    write time."""
    data = _load(state_dir)
    campaign = get_campaign(campaign_id, state_dir or _state_dir())
    reg = _registry()
    reg.assert_no_bleed(campaign["world_id"])
    sections = _parse_state_md(state_md)
    baseline = {
        "imported_at": _utcnow_iso(),
        "source": os.path.abspath(state_md),
        "sections": sections,
    }
    campaign["baseline"] = reg.label(campaign["world_id"], baseline)
    data["campaigns"][campaign_id] = campaign
    _save(data, state_dir)
    return campaign["baseline"]


def record_turn(campaign_id: str, *, actor: str, action: str,
                scene: str = "", roll_expression: str | None = None,
                roll: dict | None = None, outcome: str = "",
                threads_updated: list | None = None,
                at: str | None = None, provenance: dict | None = None,
                emit=None, state_dir: str | None = None) -> dict:
    """Record one turn. New rolls are thrown by the engine (mechanical);
    imported session history passes its documented roll verbatim with
    provenance — never re-rolled, never invented."""
    emit = emit or _default_emit
    data = _load(state_dir)
    campaign = get_campaign(campaign_id, state_dir or _state_dir())
    reg = _registry()
    reg.assert_no_bleed(campaign["world_id"])
    if roll_expression is not None and roll is not None:
        raise ValueError("pass roll_expression or roll, not both")
    if roll_expression is not None:
        thrown = engine_roll(roll_expression)
        thrown["thrown_at"] = _utcnow_iso()
        roll = thrown
    turn = {
        "n": len(campaign["turns"]) + 1,
        "at": at or _utcnow_iso(),
        "scene": scene,
        "actor": actor,
        "action": action,
        "roll": roll,
        "outcome": outcome,
        "threads_updated": list(threads_updated or []),
        "provenance": provenance or {"live": True},
    }
    labeled = reg.label(campaign["world_id"], turn)
    campaign["turns"].append(labeled)
    data["campaigns"][campaign_id] = campaign
    _save(data, state_dir)
    emit("ttrpg_turn", {"campaign_id": campaign_id,
                        "campaign_name": campaign["name"],
                        "turn": labeled})
    return labeled


def get_log(campaign_id: str, state_dir: str | None = None) -> list:
    return get_campaign(campaign_id, state_dir)["turns"]


def get_baseline(campaign_id: str, state_dir: str | None = None) -> dict | None:
    return get_campaign(campaign_id, state_dir)["baseline"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cmd_register(a) -> int:
    c = register_campaign(a.id, a.name, a.world)
    print(f"campaign {c['id']!r} registered on world {c['world_id']!r}")
    return 0


def _cmd_import_baseline(a) -> int:
    b = import_baseline(a.id, a.state_md)
    print(f"baseline imported for {a.id!r}: "
          f"{len(b['content']['sections'])} sections, "
          f"reality={b['reality']}")
    return 0


def _cmd_record_turn(a) -> int:
    turn = record_turn(a.id, actor=a.actor, action=a.action, scene=a.scene,
                       roll_expression=a.roll, outcome=a.outcome,
                       threads_updated=a.thread or [])
    c = turn["content"]
    print(f"turn {c['n']} recorded for {a.id!r} [{turn['reality']}]")
    if c["roll"]:
        print(f"  roll {c['roll']['expression']} -> {c['roll']['total']} "
              f"({c['roll']['source']})")
    return 0


def _cmd_log(a) -> int:
    for t in get_log(a.id):
        c = t["content"]
        print(f"--- turn {c['n']} [{t['reality']}] {c['at'][:16]}")
        print(f"    {c['actor']}: {c['action'][:90]}")
        if c["roll"]:
            print(f"    roll {c['roll']['expression']} -> {c['roll']['total']}")
        if c["outcome"]:
            print(f"    outcome: {c['outcome'][:90]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ttrpg.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register")
    r.add_argument("id"); r.add_argument("name"); r.add_argument("--world", required=True)
    r.set_defaults(fn=_cmd_register)
    b = sub.add_parser("import-baseline")
    b.add_argument("id"); b.add_argument("--state-md", required=True)
    b.set_defaults(fn=_cmd_import_baseline)
    t = sub.add_parser("record-turn")
    t.add_argument("id"); t.add_argument("--actor", required=True)
    t.add_argument("--action", required=True); t.add_argument("--scene", default="")
    t.add_argument("--roll", default=None); t.add_argument("--outcome", default="")
    t.add_argument("--thread", action="append", default=None)
    t.set_defaults(fn=_cmd_record_turn)
    lg = sub.add_parser("log"); lg.add_argument("id")
    lg.set_defaults(fn=_cmd_log)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
