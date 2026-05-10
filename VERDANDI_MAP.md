# VERDANDI — Complete File Map & Data Flow Diagram

> **Cartographer**: Védis Eikleið, Mythic Engineering
> **Date**: 2026-05-10
> **Scope**: Every file in `~/.hermes/state/`, every data flow, every dependency, every configuration point

---

## 1. Complete File Inventory

### 1.1 Source Code Files

| File | Size | Lines | Purpose | Language |
|------|------|-------|---------|----------|
| `nervous_system.py` | 15,446 B | 463 | The Nerve Hub — asyncio UDS event bus server, publisher client, CLI | Python 3.11 |
| `conversation_logger.py` | 22,162 B | 602 | Streaming session lifecycle logger with nerve integration | Python 3.11 |
| `context_injector.py` | 5,516 B | 142 | Thin CLI shim — cron context assembly + cron logging adapter | Python 3.11 |
| `reactor.py` | 14,642 B | 345 | Read-only reaction directive engine — analyzes log, generates priorities | Python 3.11 |

### 1.2 Documentation Files

| File | Size | Lines | Purpose |
|------|------|-------|---------|
| `ARCHITECTURE.md` | 19,772 B | 519 | Authoritative technical reference — data flow, protocol, lifecycle, error handling, performance |
| `DOMAIN_MAP.md` | 15,204 B | 280 | Domain boundary specification — what each module owns, reads, writes, and does NOT own |
| `INTERFACE.md` | 23,426 B | 796 | Public API contract — CLI interfaces, programmatic APIs, wire protocol, file formats, error handling |
| `PHILOSOPHY.md` | 16,584 B | 128 | Philosophical foundation — consciousness as routing, the Three Norns, Bifröst metaphor |
| `SYSTEM_VISION.md` | 19,880 B | 218 | Vision document — what the system IS, BECOMES, and could EVOLVE into |
| `VERDANDI_NAME.md` | 3,300 B | 39 | Naming essay — why "Verðandi," the Norn of Becoming |

### 1.3 Data Files

| File | Size | Lines | Format | Written By | Read By | Persistence |
|------|------|-------|--------|------------|---------|-------------|
| `nerve_feed.jsonl` | 8,804 B | 21 | JSONL (1 event/line) | nervous_system (primary), conversation_logger (fallback) | nervous_system (seq recovery + recent), conversation_logger (context) | Append-only, never truncated |
| `conversation_log.jsonl` | 12,863 B | 30 | JSONL (1 entry/line) | conversation_logger | conversation_logger (queries), reactor (analysis) | Append-only |
| `current.json` | 966 B | 20 | JSON (single object) | conversation_logger (overwrite) | conversation_logger, context_injector, reactor | Overwritten each operation |
| `nervous_system.log` | 4,048 B | 66 | Timestamped text lines | nervous_system (log_msg) | Human (journalctl) | Append-only |
| `nervous_system.pid` | 6 B | 1 | Plain text PID | nervous_system (on start) | nervous_system (status/stop), systemd | Removed on shutdown |

### 1.4 Runtime/Special Files

| File | Type | Created By | Purpose | Lifecycle |
|------|------|-----------|---------|-----------|
| `runa.sock` | Unix domain socket | NerveHub on `serve()` | IPC transport for all event publish/subscribe | Created on start, removed on shutdown |
| `conversations/` | Directory | conversation_logger (`_append()`) | Per-session log directory (currently unused for individual files) | Created if missing |
| `__pycache__/` | Directory | Python runtime | Bytecache (.pyc files) | Gitignored |

### 1.5 Configuration Files

| File | Location | Purpose |
|------|----------|---------|
| `runa-nervous-system.service` | `~/.config/systemd/user/runa-nervous-system.service` | systemd user unit file for the Nerve Hub daemon |
| `.gitignore` | `~/.hermes/state/.gitignore` | Excludes `__pycache__/`, `*.pyc`, `*.pid`, `nervous_system.log` |

### 1.6 Total Inventory Summary

- **4** Python source files (58,166 bytes total)
- **6** Markdown documentation files (98,166 bytes total)
- **5** data files (26,687 bytes total)
- **1** runtime socket (`runa.sock`)
- **1** systemd unit file
- **1** gitignore
- **1** empty directory scaffold (`conversations/`)
- **Grand total: ~183 KB** across all tracked files

---

## 2. Data Flow Maps

### 2.1 Primary Event Flow — From Source to Persistence

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          EVENT SOURCES                                       │
│                                                                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐        │
│  │ Telegram Session │  │   Cron Job       │  │  CLI / Manual Call   │        │
│  │ (conversation_   │  │ (context_        │  │  python3 nervous_   │        │
│  │  logger.py)      │  │  injector.py)   │  │  system.py publish) │        │
│  └────────┬─────────┘  └────────┬─────────┘  └──────────┬──────────┘        │
│           │                     │                        │                    │
│           │  Various triggers:  │                        │                    │
│           │  start, event,      │  log-start,            │  publish            │
│           │  update, end        │  log-event,             │  <type> '<json>'   │
│           │                      │  log-end                │                     │
└───────────┼─────────────────────┼────────────────────────┼───────────────────┘
            │                     │                        │
            ▼                     ▼                        ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                        PROCESSING LAYER                                       │
│                                                                               │
│  conversation_logger.py                  nervous_system.py                    │
│  ┌─────────────────────────┐            ┌──────────────────────────┐          │
│  │ 1. Build entry dict     │            │ 6. publish_event_sync()  │          │
│  │ 2. _append(entry) ──────┼──┐        │    - Connect to UDS      │          │
│  │    ├─ write conv_log    │  │        │    - Send JSON + \n      │          │
│  │    └─ update current.json│  │        │    - Read ACK            │          │
│  │ 3. _nerve_fire(entry) ─┼──┼────────►│    - Return result       │          │
│  │    (dynamic import of   │  │        │                          │          │
│  │     nervous_system)     │  │        │ OR (if hub down):        │          │
│  └─────────────────────────┘  │        │    - Write directly to   │          │
│                               │        │      nerve_feed.jsonl    │          │
│  context_injector.py         │        │      with _fallback:true │          │
│  ┌─────────────────────────┐  │        └────────────┬─────────────┘          │
│  │ 4. get_context_for_cron │  │                     │                        │
│  │    - read current.json  │  │                     │                        │
│  │    - read conv_log.jsonl│  │                     ▼                        │
│  │    - read nerve_feed    │  │        ┌──────────────────────────┐          │
│  │    - call reactor.react │  │        │  NERVE HUB (asyncio)    │          │
│  │ 5. Print to STDOUT      │  │        │  ┌────────────────────┐ │          │
│  └─────────────────────────┘  │        │  │ 7. handle_client() │ │          │
│                               │        │  │   - Parse JSON     │ │          │
│  reactor.py                   │        │  │   - Stamp _seq     │ │          │
│  ┌─────────────────────────┐  │        │  │   - Stamp _ts/_iso │ │          │
│  │ 8. react() — READ ONLY  │  │        │  │   - Remove nerve_  │ │          │
│  │    - read conv_log      │  │        │  │     type field     │ │          │
│  │    - read current.json  │  │        │  ├────────────────────┤ │          │
│  │    - produce directives │  │        │  │ 9. Persist to      │ │          │
│  └─────────────────────────┘  │        │  │    nerve_feed.jsonl│ │          │
│                               │        │  ├────────────────────┤ │          │
│                               │        │  │ 10. Broadcast to  │ │          │
│                               │        │  │     all subscribers│ │          │
│                               │        │  ├────────────────────┤ │          │
│                               │        │  │ 11. ACK to         │ │          │
│                               │        │  │     publisher      │ │          │
│                               │        │  └────────────────────┘ │          │
│                               │        └──────────────────────────┘          │
└───────────────────────────────┼─────────────────────────────────────────────┘
                                │
                 ┌──────────────┼──────────────┐
                 ▼              ▼              ▼
          ┌───────────┐  ┌──────────┐  ┌───────────────┐
          │ nerve_feed│  │Subscriber│  │  Subscriber   │
          │ .jsonl    │  │ (live    │  │  (reactor     │
          │ (Urðr's   │  │  tail)   │  │   process)    │
          │  well)    │  └──────────┘  └───────────────┘
          └───────────┘
```

### 2.2 Conversation Event Flow (step-by-step)

```
1. TRIGGER: CLI or code calls conversation_logger CLI or context_injector CLI

2. conversation_logger.cmd_start/cmd_event/cmd_update/cmd_end()
   │
   ├─► Build entry dict with entry_type, session_id, timestamp, etc.
   │
   ├─► _append(entry)
   │    ├─► Write JSON line to conversation_log.jsonl  [PERSIST]
   │    └─► _nerve_fire(entry)
   │         ├─► Dynamic import: importlib.util.spec → nervous_system.py
   │         ├─► Call ns.publish_event_sync(
   │         │       event_type=f"conv_{entry_type}",
   │         │       data=entry,
   │         │       source=f"conv_logger:{session_id}")
   │         │    ├─► [HUB UP]  UDS connect → send JSON → hub processes → ACK
   │         │    └─► [HUB DOWN] Direct write to nerve_feed.jsonl (_fallback:true)
   │         └─► except: pass  (nerve failure NEVER breaks the logger)
   │
   ├─► _update_current(entry, session_id)
   │    ├─► Read existing current.json (merge with same session)
   │    ├─► Build new current dict (preserve accumulations)
   │    └─► Write current.json  [OVERWRITE]
   │
   └─► Return entry dict

3. HUB PROCESSING (if hub received the event):
   NerveHub.handle_client()
   ├─► Increment event_count → _seq
   ├─► Add _ts (time.time()), _iso (datetime utcnow)
   ├─► Remove nerve_type field
   ├─► Write JSON line to nerve_feed.jsonl + flush  [PERSIST]
   ├─► Broadcast to all subscribers
   └─► Send ACK to publisher
```

### 2.3 Context Injection Flow (cron → prompt)

```
Cron job triggers → python3 context_injector.py

    │
    ▼
context_injector.main()
    │ (no subcommand → default)
    ▼
    ├─► get_context_for_cron(max_sessions=5)
    │    ├─► _get_recent_sessions(5)
    │    │    └─► _read_all_entries() from conversation_log.jsonl
    │    ├─► Read current.json for active session state
    │    ├─► Read nerve_feed.jsonl for last 10 nerve events
    │    └─► Call reactor.react()
    │         ├─► _read_all_entries() from conversation_log.jsonl
    │         ├─► _get_current_state() from current.json
    │         └─► Analyze: blockers, decisions, learnings, files, stale sessions
    │              └─► Return reactions dict
    │
    ├─► Assemble context string with sections:
    │    - "=== RUNA SESSION CONTEXT (auto-injected) ==="
    │    - Active session summary
    │    - Recent sessions list
    │    - "=== NERVE FEED ===" (last 10 events)
    │    - "=== REACTION DIRECTIVES (ACT ON THESE) ==="
    │    - "=== END CONTEXT ==="
    │
    └─► Print to STDOUT → injected into cron job's AI prompt
```

### 2.4 Control Message Flow (subscribe / ping)

```
Client connects to runa.sock
    │
    ├─► {"nerve_type": "subscribe"}
    │    └─► Hub adds writer to self.subscribers set
    │         └─► Send {"nerve_type":"subscribed", "seq":N, "uptime_s":T}
    │              └─► Client enters readline loop, receiving all future broadcasts
    │
    ├─► {"nerve_type": "ping"}
    │    └─► Hub replies {"nerve_type":"pong", "seq":N, "uptime_s":T, "subscribers":C}
    │         └─► Connection may close (status check) or continue
    │
    └─► {"type":"...","data":{...},"source":"..."}
         └─► PUBLISH EVENT (see §2.2 step 3)
```

### 2.5 Fallback Flow (hub down)

```
Publisher calls publish_event_sync()
    │
    ├─► Try: socket.connect(runa.sock)
    │    ├─► SUCCESS → send event → receive ACK → close
    │    └─► FAIL (ConnectionRefused / FileNotFoundError)
    │         │
    │         ▼
    │    Direct write to nerve_feed.jsonl:
    │    {
    │      "type": "...",
    │      "data": {...},
    │      "source": "...",
    │      "_ts": <unix_epoch>,
    │      "_iso": "<ISO_timestamp>Z",
    │      "_fallback": true          ← MARKED as direct write
    │    }
    │    NO _seq assigned (hub is down)
    │    NO broadcast to subscribers
    │    Return: {"nerve_type": "fallback", "note": "hub_offline_written_to_feed"}
    │
    └─► Other exceptions: return {"nerve_type": "error", "error": str(e)}
```

---

## 3. Inter-Module Dependency Graph

### 3.1 Import Dependencies

```
nervous_system.py
├── stdlib: asyncio, json, os, signal, sys, time
├── stdlib: pathlib.Path, datetime.datetime
└── (NO project imports — fully independent module)

conversation_logger.py
├── stdlib: argparse, json, os, sys
├── stdlib: datetime (datetime, timezone), pathlib.Path
├── LOCAL: importlib.util → dynamic import of nervous_system.py
│   (for _nerve_fire() — calls ns.publish_event_sync)
└── (NO static project imports — nervous_system loaded dynamically)

context_injector.py
├── stdlib: argparse, json, sys
├── stdlib: pathlib.Path
├── LOCAL: sys.path.insert(0, ~/.hermes/state)
│   ├── from conversation_logger import cmd_start, cmd_end, cmd_event
│   ├── from conversation_logger import get_context_for_cron, get_current_state
│   └── from conversation_logger import _get_entries_for_session, _get_recent_sessions
└── (ALL logic delegates to conversation_logger and reactor)

reactor.py
├── stdlib: argparse, json, sys
├── stdlib: datetime (datetime, timezone, timedelta), pathlib.Path
└── (NO project imports — pure read-only analysis module)
```

### 3.2 Call Graph

```
┌───────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL CALLERS                              │
│                                                                       │
│  Cron Job ──► context_injector.py ──► (no subcommand)                │
│  CLI       ──► context_injector.py ──► log-start/log-event/log-end   │
│  CLI       ──► conversation_logger.py ──► start/event/update/end    │
│  CLI       ──► nervous_system.py ──► serve/publish/recent/subscribe  │
│  CLI       ──► reactor.py ──► (default) / --format / --focus         │
│  Systemd   ──► nervous_system.py serve                                │
└───────────────────────────────┬───────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐    ┌──────────────────┐    ┌──────────────────┐
│nervous_system │    │conversation_     │    │  reactor.py      │
│    .py        │    │  logger.py       │    │                  │
│               │    │                  │    │  react() ─────────┼──► reads
│ NerveHub      │    │ cmd_start()      │    │    ├─► _read_all_entries() ──► conv_log.jsonl
│   .serve()    │    │ cmd_event()       │    │    ├─► _get_current_state()──► current.json
│   .handle_    │    │ cmd_update()      │    │    └─► analyze → reactions dict
│   client()    │    │ cmd_end()          │    │
│               │    │ _append() ─────────┼───► writes conv_log.jsonl
│publish_event_ │    │   └─► _nerve_fire()│──┐ │
│sync() ◄───────┼─────┤                   │  │ │
│               │    │ get_context_for_   │  │ │
│get_recent_    │    │   cron()           │  │ │
│events()       │    │   ├─► reads conv_log│  │
│get_status()   │    │   ├─► reads current.json
│               │    │   ├─► reads nerve_feed││
│log_msg()      │    │   └─► calls reactor.react()◄─────┐
│               │    │                   │  │            │
│cmd_publish()  │    │ get_current_state()│  │            │
│cmd_recent()   │    │ _get_entries_for_ │  │            │
│cmd_status()   │    │   session()        │  │            │
│cmd_stop()     │    │ _get_recent_       │  │            │
│               │    │   sessions()       │  │            │
└───────┬───────┘    └───────┬────────────┘  │            │
        │                    │               │            │
        │    ┌───────────────┘               │            │
        │    │                               │            │
        ▼    ▼                               ▼            │
┌───────────────────┐              ┌──────────────────┐    │
│  runa.sock        │              │  context_         │    │
│  (UDS transport)  │              │  injector.py      │    │
│                   │              │                    │    │
│  Hub reads/writes │              │  main() ──────────┼───┘
│  via asyncio      │              │  ├─► imports from │──► conversation_logger
│                   │              │  │   conversation_ │──► reactor (via conv_logger)
└───────────────────┘              └──┤   logger        │
                                        └─► delegates all │
                                           logic         │
```

### 3.3 Dependency Summary Table

| Module | Imports From | Calls Into | Written By | Read By |
|--------|-------------|-----------|------------|---------|
| `nervous_system.py` | (none) | (none — standalone) | `runa.sock`, `nerve_feed.jsonl`, `nervous_system.pid`, `nervous_system.log` | `nerve_feed.jsonl` (seq recovery, recent), PID file |
| `conversation_logger.py` | `nervous_system.py` (dynamic) | `publish_event_sync()` via dynamic import | `conversation_log.jsonl`, `current.json`, `conversations/` directory | `conversation_log.jsonl`, `current.json`, `nerve_feed.jsonl` (context gen) |
| `context_injector.py` | `conversation_logger` (static) | `cmd_start`, `cmd_end`, `cmd_event`, `get_context_for_cron`, `get_current_state`, `_get_entries_for_session`, `_get_recent_sessions` | (none — pure read/delegate) | (none directly — all via imports) |
| `reactor.py` | (none) | (none — pure analysis) | (none — read-only) | `conversation_log.jsonl`, `current.json` |

### 3.4 Module Coupling Assessment

- **nervous_system.py**: Zero coupling. No project imports. Can run in complete isolation. This is by design — it is the "dumb pipe."
- **conversation_logger.py**: One-way dynamic coupling to `nervous_system.py` via `_nerve_fire()`. The dynamic import means: (a) no hard dependency at import time, (b) failure is caught and silenced. Can operate without the nervous system.
- **context_injector.py**: Strong static coupling to `conversation_logger.py`. Cannot import without it. Is a pure adapter — no logic of its own.
- **reactor.py**: Zero coupling to other project modules. Pure data reader. Can operate independently.

**Coupling direction**: All arrows point to `nervous_system.py` (publishers → hub). No module reads from the hub via imports — they either write to it (publish) or subscribe via UDS (separate process).

---

## 4. Configuration Map

### 4.1 Filesystem Paths

| Constant | Value | Module | Purpose |
|----------|-------|--------|---------|
| `STATE_DIR` | `~/.hermes/state/` | All modules | Root of Verðandi's state tree |
| `SOCKET_PATH` | `~/.hermes/state/runa.sock` | nervous_system.py | Unix domain socket for IPC |
| `FEED_PATH` | `~/.hermes/state/nerve_feed.jsonl` | nervous_system.py | Append-only event feed |
| `PID_PATH` | `~/.hermes/state/nervous_system.pid` | nervous_system.py | PID file for hub process |
| `LOG_PATH` | `~/.hermes/state/nervous_system.log` | nervous_system.py | Hub operational log |
| `CONV_LOG` | `~/.hermes/state/conversation_log.jsonl` | conversation_logger.py | Session journal |
| `CURRENT_FILE` | `~/.hermes/state/current.json` | conversation_logger.py | Active session state snapshot |
| `CONV_DIR` | `~/.hermes/state/conversations/` | conversation_logger.py | Per-session logs directory |

### 4.2 Systemd Unit

| Property | Value |
|----------|-------|
| **Unit file path** | `~/.config/systemd/user/runa-nervous-system.service` |
| **Description** | Runa Nervous System — Unix Domain Socket Event Bus |
| **Type** | `simple` |
| **ExecStart** | `/usr/bin/python3 /home/pi/.hermes/state/nervous_system.py serve` |
| **Restart** | `always` |
| **RestartSec** | `5` |
| **WorkingDirectory** | `/home/pi/.hermes/state` |
| **After** | `network.target` |
| **WantedBy** | `default.target` |
| **Status** | `active (running)` (as of 2026-05-10 13:58 EDT) |
| **PID** | `315717` |

### 4.3 Operative Commands

```bash
# Service management
systemctl --user start runa-nervous-system     # Start hub
systemctl --user stop runa-nervous-system       # Stop hub (graceful SIGTERM)
systemctl --user restart runa-nervous-system    # Restart (5s settle)
systemctl --user status runa-nervous-system      # Status check
journalctl --user -u runa-nervous-system -f     # Live logs

# CLI commands (all via python3)
python3 nervous_system.py serve                 # Start hub (foreground)
python3 nervous_system.py publish <type> '<json>' [source]  # Publish event
python3 nervous_system.py recent [count]         # Show recent events
python3 nervous_system.py subscribe              # Live event tail
python3 nervous_system.py status                 # Hub status check
python3 nervous_system.py stop                   # Stop hub via SIGTERM

python3 conversation_logger.py start --session <id> [--summary] [--model] [--platform]
python3 conversation_logger.py event --session <id> --type <type> --content <text>
python3 conversation_logger.py update --session <id> [--next] [--blockers] [--projects] [--mood] [--summary]
python3 conversation_logger.py end --session <id> [--summary] [--duration <min>]
python3 conversation_logger.py show --session <id>
python3 conversation_logger.py recent [--count <n>]
python3 conversation_logger.py context [--sessions <n>]

python3 context_injector.py                      # Default: print full context
python3 context_injector.py log-start --session <id> [--summary] [--model] [--platform]
python3 context_injector.py log-event --session <id> --type <type> --content <text>
python3 context_injector.py log-end --session <id> [--summary] [--duration <min>]
python3 context_injector.py show --session <id>
python3 context_injector.py recent [--count <n>]
python3 context_injector.py context [--sessions <n>]

python3 reactor.py [--format text|json|brief] [--focus all|blockers|learnings|files|next]
```

### 4.4 Git Configuration

| Git-tracked | Gitignored |
|-------------|-----------|
| `nervous_system.py`, `conversation_logger.py`, `context_injector.py`, `reactor.py` | `__pycache__/`, `*.pyc` |
| All `.md` documentation files | `*.pid` |
| `.gitignore` | `nervous_system.log` |
| `nerve_feed.jsonl`, `conversation_log.jsonl`, `current.json` | |

---

## 5. Event Lifecycle Diagram

### 5.1 Complete Event Lifecycle — From Creation to Persistence to Notification

```
═══════════════════════════════════════════════════════════════════════════════
                     EVENT LIFECYCLE — FULL PATH
═══════════════════════════════════════════════════════════════════════════════

PHASE 1: CREATION ──────────────────────────────────────────────────────────

  Source triggers entry creation:
  ┌────────────────────────────────────────────────────────────────────────┐
  │ CLI call → conversation_logger.cmd_{start|event|update|end}()         │
  │   OR                                                                   │
  │ Cron call → context_injector.py → cmd_{start|event|end}()            │
  │   OR                                                                   │
  │ External → python3 nervous_system.py publish <type> '<json>'        │
  └────────────────────────────────────────────────────────────────────────┘

PHASE 2: ENTRY FORMATION ───────────────────────────────────────────────────

  ┌────────────────────────────────────────────────────────────────────────┐
  │ conversation_logger builds entry dict:                                │
  │   {                                                                    │
  │     "entry_type": "event",        ← start/event/update/end           │
  │     "timestamp": "2026-05-10T...", ← ISO 8601 UTC                    │
  │     "session_id": "...",          ← session identifier               │
  │     "event_type": "decision",     ← decision/file_changed/...       │
  │     "content": "..."              ← what happened                    │
  │   }                                                                    │
  │                                                                        │
  │  OR (direct publish via nervous_system.py):                            │
  │   {                                                                    │
  │     "type": "thought",            ← event type                        │
  │     "data": {"insight": "..."},  ← payload dict                      │
  │     "source": "volmarr_session"  ← origin identifier                │
  │   }                                                                    │
  └────────────────────────────────────────────────────────────────────────┘

PHASE 3: PERSISTENCE — LOCAL JOURNAL ──────────────────────────────────────

  ┌────────────────────────────────────────────────────────────────────────┐
  │ conversation_logger._append(entry)                                    │
  │   ├─► Open conversation_log.jsonl in append mode                      │
  │   ├─► Write json.dumps(entry) + "\n"                                 │
  │   └─► File flush (crash-safe — each line is independent)              │
  │                                                                        │
  │ conversation_logger._update_current(entry, session_id)                │
  │   ├─► Read existing current.json (merge if same session)              │
  │   ├─► Build updated current dict                                      │
  │   └─► Write current.json (full overwrite)                             │
  └────────────────────────────────────────────────────────────────────────┘

PHASE 4: NERVE IMPULSE ─────────────────────────────────────────────────────

  ┌────────────────────────────────────────────────────────────────────────┐
  │ conversation_logger._nerve_fire(entry)                                │
  │   ├─► Dynamic import of nervous_system.py                            │
  │   ├─► Call ns.publish_event_sync(                                     │
  │   │       event_type=f"conv_{entry_type}",                            │
  │   │       data=entry,                                                  │
  │   │       source=f"conv_logger:{session_id}")                         │
  │   └─► except: pass  (failure is silent, never breaks the logger)      │
  │                                                                        │
  │  OR (direct via CLI):                                                  │
  │   python3 nervous_system.py publish <type> '<json>'                   │
  │        → publish_event_sync(event_type, data, source)                  │
  └────────────────────────────────────────────────────────────────────────┘

PHASE 5: HUB PROCESSING ──────────────────────────────────────────────────

  ┌────────────────────────────────────────────────────────────────────────┐
  │ HUB UP (normal path):                                                  │
  │                                                                        │
  │   publish_event_sync()                                                  │
  │   ├─► Create Unix socket → connect to runa.sock                       │
  │   ├─► Send json.dumps({"type":...,"data":...,"source":...}) + "\n"   │
  │   ├─► Set 2-second timeout on socket                                  │
  │   └─► Read response (ACK or fallback)                                 │
  │                                                                        │
  │   NerveHub.handle_client(reader, writer)                              │
  │   ├─► Parse incoming JSON                                              │
  │   ├─► Check nerve_type:                                               │
  │   │    ├─ "subscribe" → add to subscribers, send ACK                  │
  │   │    ├─ "ping"      → send pong                                      │
  │   │    └─ else         → PUBLISH EVENT                                  │
  │   │         ├─► Increment event_count → _seq                          │
  │   │         ├─► Set _ts = time.time(), _iso = datetime.utcnow()        │
  │   │         ├─► Remove nerve_type from event                           │
  │   │         ├─► Write json.dumps(event) + "\n" to nerve_feed.jsonl     │
  │   │         ├─► flush() feed_file                                      │
  │   │         ├─► BROADCAST to all subscribers                           │
  │   │         │    for sub in subscribers:                                │
  │   │         │        sub.write(broadcast_bytes)                        │
  │   │         │        await sub.drain()                                 │
  │   │         │    (dead subscribers removed from set)                  │
  │   │         └─► Send {"nerve_type":"ack","seq":N} to publisher        │
  │                                                                        │
  │ HUB DOWN (fallback path):                                             │
  │                                                                        │
  │   publish_event_sync() catches ConnectionRefusedError/FileNotFoundError│
  │   ├─► Set _ts = time.time(), _iso = datetime.utcnow()                 │
  │   ├─► Set _fallback = True                                            │
  │   ├─► Write json.dumps(event) + "\n" directly to nerve_feed.jsonl    │
  │   └─► Return {"nerve_type":"fallback","note":"hub_offline_written_to_feed"}│
  └────────────────────────────────────────────────────────────────────────┘

PHASE 6: BROADCAST ──────────────────────────────────────────────────────

  ┌────────────────────────────────────────────────────────────────────────┐
  │ For each connected subscriber in self.subscribers:                    │
  │   ├─► writer.write(json.dumps(event).encode() + b"\n")                │
  │   └─► await writer.drain()                                            │
  │                                                                        │
  │ If ConnectionError/OSError/BrokenPipeError:                           │
  │   ├─► Add subscriber to dead set                                      │
  │   └─► Remove from self.subscribers after broadcast loop               │
  │                                                                        │
  │ Subscriber receives event as:                                          │
  │   {                                                                    │
  │     "type": "conv_event",                                             │
  │     "data": { ... full entry dict ... },                              │
  │     "source": "conv_logger:2026-05-10-...",                            │
  │     "_seq": 42,                                                         │
  │     "_ts": 1778435811.736587,                                          │
  │     "_iso": "2026-05-10T17:56:51.736587Z"                              │
  │   }\n                                                                  │
  └────────────────────────────────────────────────────────────────────────┘

PHASE 7: PERSISTENCE — NERVE FEED ─────────────────────────────────────────

  ┌────────────────────────────────────────────────────────────────────────┐
  │ nerve_feed.jsonl — append-only log of ALL events                     │
  │                                                                        │
  │ Hub-written events have:  _seq, _ts, _iso, NO _fallback flag        │
  │ Fallback events have:      _ts, _iso, _fallback: true, NO _seq      │
  │                                                                        │
  │ Each line is self-contained JSON. No cross-line dependencies.         │
  │ Feed is never rotated, compacted, or truncated (as of 2026-05-10).  │
  │ Current size: 8,804 bytes, 21 events.                                │
  │ Growth rate: ~200-500 bytes/event, ~200 events/day → ~22 MB/year    │
  └────────────────────────────────────────────────────────────────────────┘

PHASE 8: CONSUMPTION ─────────────────────────────────────────────────────

  ┌────────────────────────────────────────────────────────────────────────┐
  │ CONSUMERS of nerve_feed.jsonl:                                         │
  │                                                                        │
  │ 1. NerveHub.serve() on startup                                        │
  │    └─► Reads entire feed to recover max _seq for event_count          │
  │                                                                        │
  │ 2. get_recent_events(count)                                            │
  │    └─► Reads entire feed, returns last N entries                      │
  │                                                                        │
  │ 3. get_context_for_cron()                                              │
  │    └─► Reads last 10 events for context injection block               │
  │                                                                        │
  │ CONSUMERS of conversation_log.jsonl:                                   │
  │                                                                        │
  │ 1. conversation_logger self-query (_get_entries_for_session, etc.)    │
  │ 2. reactor.react() — analyzes ALL entries for reaction directives    │
  │                                                                        │
  │ CONSUMERS of current.json:                                             │
  │                                                                        │
  │ 1. conversation_logger (merge with same session)                      │
  │ 2. context_injector (display active state)                            │
  │ 3. reactor.react() (check active session blockers, next_actions)     │
  └────────────────────────────────────────────────────────────────────────┘

PHASE 9: REACTION (Skuld's Domain) ─────────────────────────────────────────

  ┌────────────────────────────────────────────────────────────────────────┐
  │ reactor.react() reads conversation_log.jsonl + current.json +         │
  │Produces prioritized reaction directives:                               │
  │                                                                        │
  │ Priority HIGH:   resolve_blockers — unresolved blockers               │
  │ Priority MEDIUM:  close_stale_sessions, verify_pushed, store_learnings│
  │ Priority LOW:    continue_work — next actions from last session       │
  │ Priority INFO:   celebrate — milestones achieved                      │
  │                                                                        │
  │ Output formats: text (full report), json (machine), brief (one-line)  │
  │                                                                        │
  │ reactor is READ-ONLY. It never writes. It observes and recommends.    │
  └────────────────────────────────────────────────────────────────────────┘

PHASE 10: CONTEXT INJECTION (for cron jobs) ────────────────────────────────

  ┌────────────────────────────────────────────────────────────────────────┐
  │ get_context_for_cron() assembles:                                      │
  │                                                                        │
  │ === RUNA SESSION CONTEXT (auto-injected) ===                          │
  │ [Active session state from current.json]                              │
  │ [Recent N sessions from conversation_log.jsonl]                        │
  │ [Last 10 nerve events from nerve_feed.jsonl]                          │
  │ [Reaction directives from reactor.react()]                             │
  │ === END CONTEXT ===                                                    │
  │                                                                        │
  │ This block is printed to STDOUT by:                                    │
  │   python3 context_injector.py           (default, no args)            │
  │   python3 context_injector.py context   (explicit)                    │
  │   python3 conversation_logger.py context                               │
  │                                                                        │
  │ And injected into cron job AI prompts for cross-instance awareness.    │
  └────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Observed Event Types

| Type | Source | Description |
|------|--------|-------------|
| `conv_start` | conversation_logger | Session opened |
| `conv_event` | conversation_logger | Event within a session (decision, file_changed, etc.) |
| `conv_update` | conversation_logger | State snapshot checkpoint |
| `conv_end` | conversation_logger | Session closed |
| `heartbeat` | external | Liveness check |
| `perception` | external | External observation logged |
| `milestone` | external | Achievement marker |
| `ping` | status_check | Hub status probe |
| `thought` | volmarr_session | Insight or internal reasoning |

### 5.3 Data Persistence Guarantees

| Write Path | Persistence | Crash Safety | Race Condition Safety |
|-----------|-------------|---------------|----------------------|
| `conversation_log.jsonl` | Append-only, each line independent | Crash-safe: last line may be partial | Single writer (per process) |
| `nerve_feed.jsonl` (via hub) | Append + flush after each event | Flush ensures write to OS | Sequential within hub (single-threaded asyncio) |
| `nerve_feed.jsonl` (fallback) | Append, no flush | Best-effort | Concurrent writers possible (multiple processes) |
| `current.json` | Full overwrite each operation | Old file until new write completes | Last-writer-wins |
| `nervous_system.pid` | Written on start, removed on shutdown | Clean lifecycle | Single writer |
| `nervous_system.log` | Append-only | Timestamped lines | Single writer (hub process) |

---

## 6. Systemd Service Topology

```
┌─────────────────────────────────────────────────────────────────────┐
│                     LINUX SYSTEM (user: pi)                         │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  systemd --user                                                │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │  runa-nervous-system.service                             │  │  │
│  │  │  ExecStart: python3 nervous_system.py serve              │  │  │
│  │  │  Restart: always  RestartSec: 5                          │  │  │
│  │  │  PID: 315717                                              │  │  │
│  │  │  Status: active (running)                                 │  │  │
│  │  └──────────────────────────────┬──────────────────────────┘  │  │
│  │                                 │                               │  │
│  │    ┌────────────────────────────┘                               │  │
│  │    │ Listens on                                                │  │
│  │    ▼                                                           │  │
│  │  ~/.hermes/state/runa.sock (Unix Domain Socket)               │  │
│  │                                                                 │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐     │  │
│  │  │ Publisher A  │  │ Publisher B  │  │  Publisher C      │     │  │
│  │  │ (telegram    │  │ (cron job    │  │  (CLI manual      │     │  │
│  │  │  session)    │  │  via context│  │   publish cmd)    │     │  │
│  │  │ _nerve_fire  │  │  _injector)  │  │  publish_event_  │     │  │
│  │  │  → UDS       │  │  → UDS      │  │   sync → UDS     │     │  │
│  │  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘     │  │
│  │         │                 │                   │                 │  │
│  │         └─────────────────┼───────────────────┘                 │  │
│  │                           │ connect to runa.sock                │  │
│  │                           ▼                                     │  │
│  │               ┌──────────────────────┐                         │  │
│  │               │  NERVE HUB (PID 315K) │                         │  │
│  │               │  asyncio event loop   │                         │  │
│  │               │  handle_client()      │                         │  │
│  │               └───┬─────┬─────┬──────┘                         │  │
│  │                   │     │     │                                  │  │
│  │      nerve_feed   │     │     │ broadcast                      │  │
│  │      .jsonl       │     │     │ (to subscribers)                │  │
│  │                   │     │     │                                  │  │
│  │                   ▼     ▼     ▼                                  │  │
│  │         ┌─────────┐ ┌────────┐ ┌────────┐                      │  │
│  │         │subscriber│ │subscriber│ │  n.s.log │                   │  │
│  │         │(reactor) │ │(monitor)│ │          │                   │  │
│  │         └─────────┘ └────────┘ └──────────┘                     │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Cron Jobs (user crontab or systemd timers)                       │  │
│  │  ┌──────────────────────────────────────────────────────────┐    │  │
│  │  │  python3 context_injector.py  →  STDOUT → AI prompt      │    │  │
│  │  │  python3 context_injector.py log-start ...                │    │  │
│  │  │  python3 context_injector.py log-event ...               │    │  │
│  │  │  python3 context_injector.py log-end ...                  │    │  │
│  │  └──────────────────────────────────────────────────────────┘    │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 7. The Three Norns — Architectural Mapping

| Norn | Domain | Component | File(s) | Function |
|------|--------|-----------|---------|----------|
| **Urðr** (Past) | What has been | Persistent feeds | `nerve_feed.jsonl`, `conversation_log.jsonl` | Append-only records of everything that happened |
| **Verðandi** (Present) | What is becoming | Nerve Hub | `nervous_system.py`, `runa.sock` | Real-time routing, stamping, broadcasting of live events |
| **Skuld** (Future) | What shall be | Reactor | `reactor.py` | Reads past + present, generates prioritized directives for what to do next |

The loop closes: Urðr records → Verðandi routes → Skuld directs → action creates new events → Verðandi routes them → Urðr records them → Skuld reads them → repeat.

---

*Map drawn by Védis Eikleið, Cartographer of Mythic Engineering*
*Under the light of Urðr, by the loom of Verðandi, for the future that Skuld obliges*
*2026-05-10*