"""game_worlds — general game-state worlds (Roadmap Worlds, Slice 6).

Beyond the table: any game Volmarr plays or tracks, held as a registered
potential world with a live state sync.

- register_game(): the game_id must start with "heimr-game-", the kind is
  forced to "game", and the reality is forced to POTENTIAL. Games are play
  and imagination — the firewall never lets one be tagged manifest.
- Source adapters (configured in the data file, never hardcoded):
    statefile — read a JSON/YAML/Markdown state file, extract via key path
    api       — HTTP GET a JSON endpoint, extract via key path
    manual    — Volmarr (or Unnr) appends log entries by hand
- sync(): poll the adapter; on change, store a snapshot and emit a
  deduped `game_state` nerve event. log() auto-syncs, so a manual game
  stays live with no polling loop. Every snapshot and entry carries its
  world label (reality: potential) at write time.
- Games live in the data file ~/.hermes/state/game_worlds.json.

Usage:
  python game_worlds.py register <game-id> <name> --adapter manual --source "..."
  python game_worlds.py log <game-id> --note "..." --json '{"plays": 590}'
  python game_worlds.py sync <game-id>
  python game_worlds.py sync-all
  python game_worlds.py list
  python game_worlds.py show <game-id>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
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

GAME_ID_PREFIX = "heimr-game-"
ADAPTERS = ("statefile", "api", "manual")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".hermes", "state")


def _default_emit(event_type: str, data: dict) -> None:
    if _nerve_publish is None:
        return
    try:
        _nerve_publish(event_type, data, "game_worlds")
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


def _games_path(state_dir: str | None = None) -> str:
    return os.path.join(state_dir or _state_dir(), "game_worlds.json")


def _load(state_dir: str | None = None) -> dict:
    data = _read_json(_games_path(state_dir))
    if not isinstance(data, dict):
        data = {}
    data.setdefault("games", {})
    data.setdefault("snapshots", {})
    return data


def _save(data: dict, state_dir: str | None = None) -> None:
    _write_json(_games_path(state_dir), data)


def _registry():
    if _bootstrap_worlds is None:
        return None
    try:
        _bootstrap_worlds()
    except Exception:
        pass
    return WorldRegistry()


def _label(game_id: str) -> dict:
    """The reality firewall, stamped on every stored entry."""
    return {"world_id": game_id, "reality": REALITY_POTENTIAL}


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------
def register_game(game_id: str, name: str, adapter: str,
                  source: str = "", description: str = "",
                  adapter_config: dict | None = None,
                  state_dir: str | None = None,
                  emit=None) -> dict:
    """Register a game as a potential world. The firewall: kind is forced
    to "game" and reality is forced to potential — a game can never be
    registered as manifest."""
    if not game_id.startswith(GAME_ID_PREFIX):
        raise ValueError(
            f"game_id must start with {GAME_ID_PREFIX!r}; got {game_id!r}")
    if adapter not in ADAPTERS:
        raise ValueError(f"adapter must be one of {ADAPTERS}; got {adapter!r}")
    if WorldEntry is None:
        raise RuntimeError("worlds module unavailable")

    reg = _registry()
    if reg is not None:
        entry = WorldEntry(world_id=game_id, kind="game",
                           reality=REALITY_POTENTIAL,
                           status="active",
                           source=source or "game_worlds",
                           description=f"{name} — {description}".strip(" —"))
        reg.register(entry)

    data = _load(state_dir)
    if game_id in data["games"]:
        raise ValueError(f"game already registered: {game_id}")
    record = {
        "game_id": game_id,
        "name": name,
        "adapter": adapter,
        "source": source,
        "description": description,
        "adapter_config": adapter_config or {},
        "log": [],
        "created": _utcnow_iso(),
        **_label(game_id),
    }
    data["games"][game_id] = record
    _save(data, state_dir)
    (emit or _default_emit)("game_registered",
                            {"game_id": game_id, "name": name,
                             "adapter": adapter, **_label(game_id)})
    return record


def get_game(game_id: str, state_dir: str | None = None) -> dict | None:
    return _load(state_dir)["games"].get(game_id)


def list_games(state_dir: str | None = None) -> list[dict]:
    return list(_load(state_dir)["games"].values())


# ---------------------------------------------------------------------------
# adapters
# ---------------------------------------------------------------------------
def _dig(obj, dotted: str):
    """Extract obj['a']['b'] via dotted key path 'a.b'."""
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _poll_statefile(game: dict) -> dict:
    cfg = game.get("adapter_config") or {}
    path = os.path.expanduser(game.get("source") or cfg.get("path") or "")
    if not path or not os.path.isfile(path):
        return {"_error": "state file not found", "path": path}
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        return {"_error": f"cannot read state file: {exc}"}
    key_path = cfg.get("key_path", "")
    if path.endswith(".json"):
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            return {"_error": f"bad JSON: {exc}"}
        state = _dig(obj, key_path) if key_path else obj
        return state if isinstance(state, dict) else {"value": state}
    if path.endswith((".yaml", ".yml")):
        try:
            import yaml  # type: ignore
        except ImportError:
            return {"_error": "pyyaml not installed"}
        try:
            obj = yaml.safe_load(text)
        except Exception as exc:
            return {"_error": f"bad YAML: {exc}"}
        state = _dig(obj, key_path) if key_path else obj
        return state if isinstance(state, dict) else {"value": state}
    # markdown / text: honest change detection
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {"sha256": digest, "chars": len(text),
            "lines": text.count("\n") + 1}


def _poll_api(game: dict) -> dict:
    cfg = game.get("adapter_config") or {}
    url = game.get("source") or cfg.get("url") or ""
    if not url:
        return {"_error": "no url configured"}
    headers = {"User-Agent": "Verdandi-game-worlds/1.0"}
    headers.update(cfg.get("headers") or {})
    req = urllib.request.Request(url, headers=headers)
    timeout = float(cfg.get("timeout", 20))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", "replace")
    except Exception as exc:
        return {"_error": f"api unreachable: {exc}"}
    try:
        obj = json.loads(body)
    except json.JSONDecodeError:
        return {"_error": "api did not return JSON",
                "sha256": hashlib.sha256(body.encode()).hexdigest()}
    key_path = cfg.get("key_path", "")
    state = _dig(obj, key_path) if key_path else obj
    return state if isinstance(state, dict) else {"value": state}


def _poll_manual(game: dict) -> dict:
    log = game.get("log") or []
    if not log:
        return {}
    last = log[-1]
    state = dict(last.get("state") or {})
    state["_last_entry"] = last.get("ts")
    return state


def _poll(game: dict) -> dict:
    adapter = game.get("adapter")
    if adapter == "statefile":
        return _poll_statefile(game)
    if adapter == "api":
        return _poll_api(game)
    return _poll_manual(game)


# ---------------------------------------------------------------------------
# manual log + sync
# ---------------------------------------------------------------------------
def log_entry(game_id: str, note: str, state: dict | None = None,
              provenance: str = "", state_dir: str | None = None,
              emit=None, autosync: bool = True) -> dict:
    """Append a manual log entry. Only meaningful for manual-adapter games;
    refused for other adapters so a hand-written note can never overwrite
    a polled source."""
    data = _load(state_dir)
    game = data["games"].get(game_id)
    if game is None:
        raise ValueError(f"unknown game: {game_id}")
    if game.get("adapter") != "manual":
        raise ValueError(
            f"log_entry is only for manual-adapter games; "
            f"{game_id} uses {game.get('adapter')}")
    entry = {"ts": _utcnow_iso(), "note": note,
             "state": state or {}, "provenance": provenance,
             **_label(game_id)}
    game["log"].append(entry)
    _save(data, state_dir)
    (emit or _default_emit)("game_log_entry",
                            {"game_id": game_id, "note": note,
                             **_label(game_id)})
    if autosync:
        sync(game_id, state_dir=state_dir, emit=emit)
    return entry


def _snapshot_changed(old: dict | None, new: dict) -> bool:
    if old is None:
        return True
    return old.get("state") != new


def sync(game_id: str, state_dir: str | None = None, emit=None) -> dict:
    """Poll the adapter; on change store a labeled snapshot and emit a
    deduped game_state nerve event. Returns the sync report."""
    data = _load(state_dir)
    game = data["games"].get(game_id)
    if game is None:
        raise ValueError(f"unknown game: {game_id}")
    state = _poll(game)
    prev = data["snapshots"].get(game_id)
    report = {"game_id": game_id, "adapter": game.get("adapter"),
              "changed": _snapshot_changed(prev, state),
              **_label(game_id)}
    if report["changed"]:
        changed_keys = []
        if prev is not None:
            old_state = prev.get("state") or {}
            keys = set(old_state) | set(state)
            changed_keys = sorted(k for k in keys
                                  if not k.startswith("_")
                                  and old_state.get(k) != state.get(k))
        snapshot = {"ts": _utcnow_iso(), "state": state,
                    "changed_keys": changed_keys, **_label(game_id)}
        data["snapshots"][game_id] = snapshot
        _save(data, state_dir)
        (emit or _default_emit)("game_state",
                                {"game_id": game_id, "name": game.get("name"),
                                 "changed_keys": changed_keys,
                                 "state": state, **_label(game_id)})
        report["changed_keys"] = changed_keys
    return report


def sync_all(state_dir: str | None = None, emit=None) -> list[dict]:
    reports = []
    for game in list_games(state_dir):
        try:
            reports.append(sync(game["game_id"], state_dir=state_dir,
                                emit=emit))
        except Exception as exc:  # one bad game never blocks the rest
            reports.append({"game_id": game["game_id"], "changed": False,
                            "error": str(exc), **_label(game["game_id"])})
    return reports


def get_snapshot(game_id: str, state_dir: str | None = None) -> dict | None:
    return _load(state_dir)["snapshots"].get(game_id)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cmd_register(a) -> int:
    cfg = {}
    if a.key_path:
        cfg["key_path"] = a.key_path
    try:
        rec = register_game(a.game_id, a.name, a.adapter, source=a.source,
                            description=a.description, adapter_config=cfg)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}")
        return 1
    print(f"registered {rec['game_id']} ({rec['adapter']}) "
          f"as potential game world")
    return 0


def _cmd_log(a) -> int:
    try:
        state = json.loads(a.json) if a.json else {}
    except json.JSONDecodeError as exc:
        print(f"error: bad --json: {exc}")
        return 1
    try:
        entry = log_entry(a.game_id, a.note, state=state,
                          provenance=a.provenance)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    print(f"logged {entry['ts']} -> {a.game_id} (synced)")
    return 0


def _cmd_sync(a) -> int:
    try:
        rep = sync(a.game_id)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    if rep["changed"]:
        keys = ", ".join(rep.get("changed_keys") or ["(new)"])
        print(f"{a.game_id}: state changed [{keys}]")
    else:
        print(f"{a.game_id}: no change")
    return 0


def _cmd_sync_all(_a) -> int:
    for rep in sync_all():
        if rep.get("error"):
            print(f"{rep['game_id']}: error: {rep['error']}")
        elif rep["changed"]:
            print(f"{rep['game_id']}: state changed")
        else:
            print(f"{rep['game_id']}: no change")
    return 0


def _cmd_list(_a) -> int:
    for g in list_games():
        print(f"{g['game_id']}\t{g['name']}\t{g['adapter']}\t"
              f"{len(g.get('log', []))} log entries")
    return 0


def _cmd_show(a) -> int:
    g = get_game(a.game_id)
    if g is None:
        print(f"error: unknown game: {a.game_id}")
        return 1
    print(json.dumps(g, indent=2, ensure_ascii=False))
    snap = get_snapshot(a.game_id)
    if snap:
        print("--- snapshot ---")
        print(json.dumps(snap, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="game_worlds",
                                 description="General game-state worlds")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("register", help="register a game world")
    p.add_argument("game_id")
    p.add_argument("name")
    p.add_argument("--adapter", choices=ADAPTERS, required=True)
    p.add_argument("--source", default="")
    p.add_argument("--description", default="")
    p.add_argument("--key-path", default="")
    p.set_defaults(func=_cmd_register)

    p = sub.add_parser("log", help="append a manual log entry (auto-syncs)")
    p.add_argument("game_id")
    p.add_argument("--note", required=True)
    p.add_argument("--json", default="")
    p.add_argument("--provenance", default="")
    p.set_defaults(func=_cmd_log)

    p = sub.add_parser("sync", help="poll one game and snapshot on change")
    p.add_argument("game_id")
    p.set_defaults(func=_cmd_sync)

    p = sub.add_parser("sync-all", help="poll all games")
    p.set_defaults(func=_cmd_sync_all)

    p = sub.add_parser("list", help="list registered games")
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("show", help="show a game and its snapshot")
    p.add_argument("game_id")
    p.set_defaults(func=_cmd_show)

    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
