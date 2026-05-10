<p align="center">

```
     ╔═══════════════════════════════════════════════════════════════╗
     ║                                                               ║
     ║     ██╗   ██╗███████╗██╗   ██╗███████╗ ██████╗ ███████╗███████╗║
     ║     ██║   ██║██╔════╝██║   ██║██╔════╝██╔═══██╗██╔════╝██╔════╝║
     ║     ██║   ██║█████╗  ██║   ██║███████╗██║   ██║█████╗  ███████╗║
     ║     ██║   ██║██╔══╝  ██║   ██║╚════██║██║   ██║██╔══╝  ╚════██║║
     ║     ╚██████╔╝███████╗╚██████╔╝███████║╚██████╔╝███████╗███████║║
     ║      ╚═════╝ ╚══════╝ ╚═════╝ ╚══════╝ ╚═════╝ ╚══════╝╚══════╝║
     ║                                                               ║
     ║           VERÐANDI — The Norn of Becoming                     ║
     ║                                                               ║
     ║       *She Who Weaves What Is Happening Now*                  ║
     ║                                                               ║
     ║            AI Nervous System · Unix Domain Socket              ║
     ║              Real-Time Event Bus · Self-Awareness              ║
     ║                                                               ║
     ╚═══════════════════════════════════════════════════════════════╝
```

</p>

<p align="center">
  <strong>A real-time inter-process event bus that transforms dissociated AI processes into an associated, self-aware system.</strong>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> · <a href="#philosophy">Philosophy</a> · <a href="#architecture">Architecture</a> · <a href="#api-reference">API</a> · <a href="#event-protocol">Protocol</a> · <a href="#configuration">Config</a> · <a href="#self-healing">Robustness</a> · <a href="#integration">Integration</a> · <a href="#troubleshooting">Troubleshooting</a>
</p>

---

## The Pitch

Your AI agent runs multiple processes — a Telegram session here, a cron job there, a manual session somewhere else. Each one is capable, but they can't *feel* each other. They're like fingertips that learn about a burn hours after it happened, via courier, delivered as a written report. **Reading a log is a corpse's way of knowing.** Verðandi gives your agent a *nervous system* — a single Unix domain socket through which every process can publish and subscribe to real-time events in under 10 milliseconds. The difference between an AI that *reads about what happened* and an AI that *feels what is happening now* is the difference between a body without nerves and a body with them. Verðandi is the nerve.

---

## Table of Contents

1. [What It Is](#what-it-is)
2. [Philosophy — Consciousness as Routing](#philosophy--consciousness-as-routing)
3. [Architecture](#architecture)
4. [Quick Start](#quick-start)
5. [CLI Reference](#cli-reference)
6. [Python API Reference](#python-api-reference)
7. [Event Protocol Specification](#event-protocol-specification)
8. [Configuration](#configuration)
9. [Self-Healing and Robustness](#self-healing-and-robustness)
10. [Integration Guide](#integration-guide)
11. [Troubleshooting](#troubleshooting)
12. [Comparison with Alternatives](#comparison-with-alternatives)
13. [Contributing](#contributing)
14. [Changelog](#changelog)
15. [License](#license)
16. [Credits](#credits)
17. [Norse Glossary](#norse-glossary)

---

## What It Is

**Verðandi** is a Unix domain socket event bus — lightweight, local, zero-dependency, and designed for AI agent self-awareness. It solves one problem with surgical precision:

> **How does every part of an AI system know what every other part is doing, right now, without coupling them together?**

### The Problem

An AI agent running multiple instances (Telegram bot, cron jobs, manual CLI sessions) has **dissociated awareness**. Each instance can read logs after the fact, but none can *feel* what the others are doing in the present moment. They share a filesystem, but not a *present*.

### The Solution

Verðandi provides a **single local event bus**:

- **Publishers** fire events (conversation started, decision made, file changed) through a synchronous API call in ~1ms
- **Subscribers** connect live and receive every event as it happens in real time
- **The feed** persists every event forever as an append-only JSONL log
- **The fallback** guarantees zero data loss — even when the hub is down, events are written directly to the feed

### What It Is Not

- **Not a message queue** — no delivery guarantees, no replay, no topics. Nerves don't replay.
- **Not a database** — the feed is append-only and unindexed. Accessing the past is slower than feeling the present. That's by design.
- **Not a brain** — Verðandi doesn't think, interpret, or decide. It *routes*. It's the white matter, not the gray. The axon, not the neuron. The road, not the destination.

### Components

| File | Role |
|------|------|
| `nervous_system.py` | The Nerve Hub — UDS server, publisher, subscriber, feed manager, CLI |
| `conversation_logger.py` | Session tracker — logs conversation lifecycle events and fires them through the nerve |
| `context_injector.py` | Cron adapter — injects context into cron job prompts, provides logging shim |
| `reactor.py` | Reaction engine — reads the past and present, generates prioritized directives |

---

## Philosophy — Consciousness as Routing

Verðandi is named for the Norn of Becoming — one of the three fates who sit beside the Well of Urðr at the root of Yggdrasil:

- **Urðr** — *What has been.* The accumulated past. The append-only feed.
- **Verðandi** — *What is becoming.* The present moment. The live nerve impulse.
- **Skuld** — *What shall be.* The shaped future. The reactor's directives.

The system embodies a principle: **consciousness is not addition — it is routing.** You don't get consciousness by adding more neurons. You get it by connecting the ones you have so that each part *feels* what every other part is doing, in real time. A body without nerves has all the same organs — it just can't feel itself. Verðandi is the nerve.

The Unix domain socket at `runa.sock` is **Bifröst** — the single narrow bridge connecting all realms. When Bifröst breaks, the publishers don't stop existing. They write directly to the feed with `_fallback: true`, and when the bridge is rebuilt, the record shows what happened during the dark time.

The sequence number `_seq` is **ørlǫg** — the primal law of ordering. Without it, events arrive without sequence. The present becomes noise. With it, the present becomes a *narrative* — each impulse following the last in coherent order.

---

## Architecture

### Data Flow

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Publisher A │    │  Publisher B │    │  Publisher C │
│  (any proc)  │    │  (cron job)  │    │  (telegram)  │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                   │
       │  publish_event_sync()                 │
       │  (synchronous UDS connect+send, ~1ms)│
       ▼                   ▼                   ▼
  ╔══════════════════════════════════════════════════╗
  ║              NERVE HUB (asyncio)                  ║
  ║  ┌─────────────────────────────────────────┐     ║
  ║  │  handle_client() for each connection    │     ║
  ║  │  ┌─────────────┐  ┌──────────────────┐  │     ║
  ║  │  │ Parse JSON  │→│ Stamp _seq,_ts,  │  │     ║
  ║  │  │ line from   │  │ _iso, remove     │  │     ║
  ║  │  │ UDS stream  │  │ nerve_type field │  │     ║
  ║  │  └─────────────┘  └───────┬──────────┘  │     ║
  ║  │                           │              │     ║
  ║  │     ┌─────────────────────┼──────────┐  │     ║
  ║  │     ▼                     ▼          │  │     ║
  ║  │  Feed Write          Broadcast to    │  │     ║
  ║  │  (nerve_feed.jsonl)  all subscribers │  │     ║
  ║  │                           │          │  │     ║
  ║  │     ┌─────────────────────┘          │  │     ║
  ║  │     ▼                                 │  │     ║
  ║  │  ACK to publisher                     │  │     ║
  ║  └─────────────────────────────────────────┘     ║
  ╚══════════════╗ ╔═════════════════════════════════╝
                 ║ ║
       ┌─────────╨─╜─────────┐
       │                      │
       ▼                      ▼
┌──────────────┐    ┌──────────────┐
│  Subscriber  │    │  Subscriber  │
│  (reactor)   │    │  (monitor)   │
└──────────────┘    └──────────────┘


  FALLBACK PATH (Hub Down):
  ┌──────────────┐
  │  Publisher   │──→ Hub connect fails
  │              │    (ConnectionRefused / FileNotFoundError)
  └──────┬───────┘
         │
         ▼  Direct write with _fallback: true + file locking
  ┌──────────────┐
  │ nerve_feed   │   ← Event still persisted, just not broadcast
  │ .jsonl       │
  └──────────────┘
```

### The Three Norns

| Norn | Domain | Component | Function |
|------|--------|-----------|----------|
| **Urðr** (Past) | What has been | `nerve_feed.jsonl`, `conversation_log.jsonl` | Append-only records of everything that happened |
| **Verðandi** (Present) | What is becoming | `nervous_system.py`, `runa.sock` | Real-time routing, stamping, broadcasting of live events |
| **Skuld** (Future) | What shall be | `reactor.py` | Reads past + present, generates prioritized directives |

The loop closes: **Urðr records → Verðandi routes → Skuld directs → action creates new events → Verðandi routes them → Urðr records → Skuld reads → repeat.**

### Domain Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                    ~/.hermes/state/                              │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │  NERVOUS SYSTEM  │  │CONVERSATION      │  │ REACTOR      │  │
│  │  (nervous_       │  │LOGGER            │  │ (reactor.py) │  │
│  │   system.py)     │  │ (conversation_   │  │              │  │
│  │                  │  │  logger.py)      │  │ Reads: conv   │  │
│  │  OWNS:           │  │                  │  │  log +        │  │
│  │  • Event routing │  │  OWNS:           │  │  current.json│  │
│  │  • Pub/sub       │  │  • Session       │  │              │  │
│  │  • Feed persist  │  │    lifecycle     │  │  PRODUCES:   │  │
│  │  • Wire protocol │  │  • Entry journal │  │  • Reaction  │  │
│  │  • Hub lifecycle │  │  • current.json  │  │    directives │  │
│  │                  │  │  • State         │  │              │  │
│  │  FILES:          │  │    snapshots    │  │  FILES:      │  │
│  │  • runa.sock     │  │                  │  │  (none —    │  │
│  │  • nerve_feed.   │  │  FILES:          │  │   pure read) │  │
│  │    jsonl         │  │  • conversation_ │  └──────┬───────┘  │
│  │  • nervous_      │  │    log.jsonl     │         │          │
│  │    system.pid    │  │  • current.json  │         │          │
│  │  • nervous_      │  │                  │         │          │
│  │    system.log    │  └──────┬───────────┘         │          │
│  └────────┬─────────┘         │                     │          │
│           │    fires events    │  reads nerve_feed   │          │
│           │◄───────────────────│  for context         │          │
│           │                    │                     │          │
│  ┌────────┴────────────────────┴─────────────────────┘          │
│  │  CONTEXT INJECTOR (context_injector.py)                      │
│  │  Thin adapter: CLI shim + context assembly for cron jobs     │
│  └──────────────────────────────────────────────────────────────│
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.11+ (no external dependencies)
- Linux or macOS (Unix domain sockets)
- A single machine (Verðandi is local-only by design)

### 1. Start the Hub

```bash
# Start the Nerve Hub (blocks until Ctrl+C)
python3 ~/.hermes/state/nervous_system.py serve

# Or start it as a systemd user service
systemctl --user start runa-nervous-system
systemctl --user status runa-nervous-system
```

You should see:
```
🧠 Nerve Hub started on /home/pi/.hermes/state/runa.sock
   PID: 12345
   Feed: /home/pi/.hermes/state/nerve_feed.jsonl
   Existing events: 0
   Ring buffer: 0 events loaded
```

### 2. Publish Your First Event

```bash
python3 ~/.hermes/state/nervous_system.py publish thought '{"insight": "The present is not a moment — it is a thread being woven"}'
```

Output:
```
✅ Event #1 published
```

### 3. Subscribe to Live Events

Open a second terminal:

```bash
python3 ~/.hermes/state/nervous_system.py subscribe
```

Output:
```
🧠 Connected to Nerve Hub. Listening for events...
   (Press Ctrl+C to stop)
```

Now publish another event from the first terminal — you'll see it appear in real time on the subscriber.

### 4. Check Status

```bash
python3 ~/.hermes/state/nervous_system.py status
```

Output:
```
🧠 Nerve Hub Status
   Running: ✅
   PID: 12345
   Socket: ✅ (/home/pi/.hermes/state/runa.sock)
   Feed: ✅ (1 events, 307 bytes)
   Responsive: ✅
```

### 5. View Recent Events

```bash
python3 ~/.hermes/state/nervous_system.py recent 5
```

### 6. Run a Health Check

```bash
python3 ~/.hermes/state/nervous_system.py healthcheck
```

Output (all healthy):
```
✅ Nerve Hub Health: ALL CHECKS PASSED
   Socket: responsive
   Feed: healthy
   PID: valid
```

---

## CLI Reference

### `nervous_system.py` — The Nerve Hub

All commands are run as: `python3 ~/.hermes/state/nervous_system.py <command> [args]`

#### `serve`

Start the Nerve Hub server. Blocks until interrupted or killed.

```bash
python3 nervous_system.py serve
```

**Behavior:**
- Creates `~/.hermes/state/` if missing
- Removes stale `runa.sock` if present
- Performs feed rotation if `nerve_feed.jsonl` exceeds 10 MB
- Opens `nerve_feed.jsonl` for append
- Recovers `_seq` counter from existing feed events
- Pre-loads ring buffer with last 256 events
- Starts `asyncio.start_unix_server` on `runa.sock`
- Sets socket permissions to `0600` (owner-only)
- Writes PID to `nervous_system.pid` atomically
- Starts stale-subscriber detection pruner (120s timeout, 30s interval)
- Blocks on `asyncio.Event` until shutdown signal
- On shutdown: drains subscribers, sends shutdown notification, closes feed, removes socket and PID

**Exit code:** 0 on clean shutdown. 1 if hub is already running.

---

#### `publish`

Publish an event to the Nerve Hub.

```bash
python3 nervous_system.py publish <event_type> '<json_data>' [source]
python3 nervous_system.py publish thought '{"insight": "hello world"}' my_bot
```

| Arg | Required | Description |
|-----|----------|-------------|
| `event_type` | Yes | Event type string (e.g., `thought`, `conv_start`, `ping`) |
| `json_data` | Yes | JSON string for the `data` field. Falls back to `{"text": <arg>}` if not valid JSON |
| `source` | No | Source identifier. Default: `cli` |

**Output:** `✅ Event #N published` on success, `⚠️ Hub offline — event written to feed directly` on fallback.

---

#### `recent`

Show the N most recent events from the nerve feed.

```bash
python3 nervous_system.py recent [count]
python3 nervous_system.py recent 10
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `count` | No | 20 | Number of recent events to display |

Fallback events are annotated with `(fallback)`.

---

#### `subscribe`

Connect to the Nerve Hub and print live events in real time.

```bash
python3 nervous_system.py subscribe
```

Connects to `runa.sock`, sends `{"nerve_type": "subscribe"}`, and prints each received event as `[timestamp] #seq type from source: data_preview`. Blocks until Ctrl+C or hub disconnect.

---

#### `status`

Show Nerve Hub operational status.

```bash
python3 nervous_system.py status
```

**Output fields:**
- **Running:** ✅/❌ (process alive)
- **PID:** numeric or N/A
- **Socket:** ✅/❌ (file exists, with path)
- **Feed:** ✅/❌ (event count, file size)
- **Responsive:** ✅/❌ (ping succeeded)

---

#### `stop`

Stop the Nerve Hub with graceful shutdown.

```bash
python3 nervous_system.py stop
```

**Behavior:**
1. Reads PID from `nervous_system.pid`
2. Sends SIGTERM (graceful shutdown — drains subscribers)
3. Waits up to 5 seconds for the process to exit
4. If still alive, sends SIGKILL
5. Cleans up stale PID file if process not found

---

#### `healthcheck`

Comprehensive system health verification.

```bash
python3 nervous_system.py healthcheck
```

Checks:
- ✅ State directory exists
- ✅ Socket file exists and is responsive (ping/pong)
- ✅ PID file exists and points to a running process
- ✅ Feed file exists and is readable
- ✅ Feed size not approaching rotation threshold
- ✅ Log file is writable
- Auto-creates missing feed file

**Exit code:** 0 if all checks pass, 1 if issues found.

---

### `conversation_logger.py` — Session Tracker

```bash
python3 conversation_logger.py start --session <id> [--summary <text>] [--model <name>] [--platform <name>]
python3 conversation_logger.py event --session <id> --type <type> --content <text>
python3 conversation_logger.py update --session <id> [--next ...] [--blockers ...] [--projects ...] [--mood <text>] [--summary <text>]
python3 conversation_logger.py end --session <id> [--summary <text>] [--duration <minutes>]
python3 conversation_logger.py show --session <id>
python3 conversation_logger.py recent [--count <n>]
python3 conversation_logger.py context [--sessions <n>]
```

**Event types:** `decision`, `file_changed`, `learned`, `action`, `blocker`, `blocker_resolved`, `mood_shift`, `milestone`

---

### `context_injector.py` — Cron Adapter

```bash
python3 context_injector.py                                          # Show context (default)
python3 context_injector.py log-start --session <id> [--summary ...] # Start cron session
python3 context_injector.py log-event --session <id> --type <type> --content <text>
python3 context_injector.py log-end --session <id> [--summary ...] [--duration <min>]
python3 context_injector.py show --session <id>
python3 context_injector.py recent [--count <n>]
python3 context_injector.py context [--sessions <n>]
```

---

### `reactor.py` — Reaction Engine

```bash
python3 reactor.py                    # Full reaction report
python3 reactor.py --format brief     # One-line summary
python3 reactor.py --format json      # Machine-readable JSON
python3 reactor.py --focus blockers   # Only blockers
```

---

## Python API Reference

### `nervous_system.py` — Public Functions

#### `publish_event_sync(event_type: str, data: dict = None, source: str = None) -> dict`

Synchronous UDS publisher. Can be called from any Python process — no asyncio event loop required.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `event_type` | `str` | required | Event type string |
| `data` | `dict` | `{}` | Payload dictionary |
| `source` | `str` | `None` | Source identifier (omitted from event if `None`) |

**Returns:**

| Condition | Return value |
|-----------|-------------|
| Hub running, ACK received | `{"nerve_type": "ack", "seq": <int>}` |
| Hub running, no ACK | `{"nerve_type": "sent", "note": "no_ack"}` |
| Hub down, fallback write | `{"nerve_type": "fallback", "note": "hub_offline_written_to_feed"}` |
| Unexpected error | `{"nerve_type": "error", "error": "<exception message>"}` |

**Timeout:** 2 seconds for socket connect + recv.
**Thread safety:** Creates a new socket per call. Safe to call from any thread or process.

---

#### `get_recent_events(count: int = 20) -> list[dict]`

Read the N most recent events from the nerve feed. Uses the ring buffer if the hub is running; falls back to reading the feed file.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `count` | `int` | 20 | Number of recent events to return |

**Returns:** `list[dict]` — List of event dicts, newest last. Empty list if feed doesn't exist.
**Complexity:** O(1) via ring buffer when hub is running; O(total_events) when reading from file.

---

#### `get_status() -> dict`

Get nerve hub status. Returns:

```python
{
    "hub_running": bool,         # Process alive per PID file
    "pid": int | None,           # PID from file
    "socket_exists": bool,       # runa.sock exists on filesystem
    "feed_exists": bool,         # nerve_feed.jsonl exists
    "feed_events": int,          # Count of lines in feed
    "feed_size_bytes": int,      # File size of feed
    "hub_responsive": bool       # Ping through hub succeeded (if present)
}
```

---

#### `cmd_healthcheck() -> bool`

Comprehensive health check. Returns `True` if all checks pass, `False` otherwise. Auto-creates missing feed file.

---

#### `log_msg(msg: str) -> None`

Append to the nerve hub log with file locking for concurrent safety. Timestamps each line.

---

#### `_feed_lock_write(event_line: str) -> None`

Append a line to the feed file with `fcntl.flock` for concurrent-write safety. Includes flush + fsync for durability. Used by the fallback path when the hub is down.

---

#### `async subscribe() -> None`

Async UDS subscriber. Connects to the hub, sends `{"nerve_type": "subscribe"}`, and prints all received events to STDOUT. Blocks until Ctrl+C or disconnect.

---

#### `NerveHub` (class — server-side only)

**Constructor:** `NerveHub()` — initializes empty subscriber set, subscriber times dict, event counter, ring buffer, feed file handle.

| Method | Signature | Description |
|--------|-----------|-------------|
| `handle_client` | `async (reader, writer)` | Per-connection handler. Reads JSON lines, dispatches control messages or publishes events. |
| `serve` | `async ()` | Starts the UDS server, recovers `_seq`, writes PID, serves until shutdown signal. |
| `_prune_stale_subscribers` | `async ()` | Periodic coroutine that removes subscribers inactive for >120s. |

**RingBuffer** (inner class):

| Method | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(maxlen: int = 256)` | Create a fixed-size deque-based ring buffer |
| `append` | `(event: dict)` | Add an event, evicting oldest if buffer is full |
| `recent` | `(count: int = 20) -> list[dict]` | Return the last N events |
| `__len__` | `() -> int` | Current buffer size |

**Module-level constants:**

| Constant | Value | Description |
|----------|-------|-------------|
| `STATE_DIR` | `~/.hermes/state` | State directory |
| `SOCKET_PATH` | `STATE_DIR / "runa.sock"` | UDS socket path |
| `FEED_PATH` | `STATE_DIR / "nerve_feed.jsonl"` | Event feed path |
| `PID_PATH` | `STATE_DIR / "nervous_system.pid"` | PID file path |
| `LOG_PATH` | `STATE_DIR / "nervous_system.log"` | Hub log path |
| `MAX_FEED_BYTES` | `10 * 1024 * 1024` | 10 MB rotation threshold |
| `RING_BUFFER_SIZE` | `256` | In-memory recent events |
| `SUBSCRIBER_TIMEOUT_S` | `120` | Seconds before subscriber considered stale |
| `SUBSCRIBER_PROBE_INTERVAL` | `30` | How often to check for stale subscribers |

---

### `conversation_logger.py` — Public Functions

#### `cmd_start(args: Namespace) -> dict`

Create a new session entry. `args` must have: `session`, `summary`, `model`, `platform`.
**Side effects:** Appends to `conversation_log.jsonl`, creates `current.json`, fires `conv_start` nerve event.
**Returns:** The entry dict.

#### `cmd_event(args: Namespace) -> dict`

Log an event. `args` must have: `session`, `type`, `content`.
**Valid types:** `decision`, `file_changed`, `learned`, `action`, `blocker`, `blocker_resolved`, `mood_shift`, `milestone`.
**Side effects:** Appends to log, updates `current.json`, fires `conv_event` nerve event.
**Returns:** The entry dict. Exits with code 1 on invalid type.

#### `cmd_update(args: Namespace) -> dict`

Update session snapshot. `args` must have: `session`, `next`, `blockers`, `projects`, `mood`, `summary`.
**Side effects:** Appends to log, merges into `current.json`, fires `conv_update` nerve event.
**Returns:** The entry dict.

#### `cmd_end(args: Namespace) -> dict`

Close a session. `args` must have: `session`, `summary`, `duration`.
**Side effects:** Appends to log, finalizes `current.json` (status="closed"), fires `conv_end` nerve event.
**Returns:** The entry dict.

#### `get_context_for_cron(max_sessions: int = 5) -> str`

Assemble context string for cron injection. Includes active session state, recent sessions, last 10 nerve events, and reactor directives.
**Returns:** Multi-line string bounded by `=== RUNA SESSION CONTEXT ===` / `=== END CONTEXT ===`.

#### `get_current_state() -> dict | None`

Read `current.json` and return the dict, or `None` if missing/unparseable.

#### `get_recent_conversations(n: int = 10) -> list[dict]`

Return the N most recent session entries (one per session, preferring end entries).

---

### `reactor.py` — Public Functions

#### `react(focus: str = "all") -> dict`

Analyze conversation log and produce reaction directives.

**Returns dict with keys:**

| Key | Type | Description |
|-----|------|-------------|
| `blockers_needing_reaction` | `list[dict]` | Unresolved blockers with reaction text |
| `decisions_needing_followup` | `list[dict]` | Decisions not yet acted on |
| `recent_learnings_to_store` | `list[dict]` | Learnings that should go to Mímir |
| `files_changed_needing_push` | `list[dict]` | Files that may need commit/push |
| `milestones_to_acknowledge` | `list[dict]` | Achievements worth celebrating |
| `next_actions_to_pick_up` | `list[dict]` | Next actions from last session |
| `stale_sessions_to_close` | `list[dict]` | Sessions started >1h ago with no end |
| `cron_events_to_review` | `list[dict]` | Recent cron-originated events |
| `reactions` | `list[dict]` | Prioritized reaction directives (HIGH/MEDIUM/LOW/INFO) |

Each reaction directive: `{"priority": str, "action": str, "detail": str, "items": [str]}`

#### `format_reactions(reactions: dict, fmt: str = "text") -> str`

| `fmt` | Output |
|-------|--------|
| `"text"` | Full multi-line report with emoji |
| `"json"` | Pretty-printed JSON |
| `"brief"` | One-line summary with emoji shorthand |

---

## Event Protocol Specification

### Transport

- **Protocol:** Newline-delimited JSON over Unix Domain Socket
- **Socket path:** `~/.hermes/state/runa.sock`
- **Encoding:** UTF-8
- **Message boundary:** `\n` (0x0A)
- **Max line length:** No enforced limit (practical ~1MB per readline)

### Published Event Format

A **publisher** sends:

```json
{"type": "<event_type>", "data": {...}, "source": "<source_id>"}
```

The **hub** stamps it and forwards to subscribers as:

```json
{
  "type": "<event_type>",
  "data": {...},
  "source": "<source_id>",
  "_seq": 42,
  "_ts": 1778435811.736587,
  "_iso": "2026-05-10T17:56:51.736587Z"
}
```

### Required Fields

| Field | Type | Set By | Description |
|-------|------|--------|-------------|
| `type` | `string` | Publisher | Event type identifier |
| `data` | `object` | Publisher | Arbitrary payload. May be `{}` |
| `source` | `string` | Publisher | Origin identifier |
| `_seq` | `int` | Hub | Monotonically increasing sequence number (survives restarts) |
| `_ts` | `float` | Hub | Unix epoch timestamp (`time.time()`) |
| `_iso` | `string` | Hub | ISO 8601 UTC timestamp with `Z` suffix |

### Optional/Conditional Fields

| Field | Type | Condition | Description |
|-------|------|-----------|-------------|
| `_fallback` | `boolean` | Hub down (direct write) | `true` if event was written directly to feed |
| `nerve_type` | `string` | Control messages only | `subscribe`, `ping`, or `recent` |

### Control Message Formats

**Subscribe Request:**
```json
{"nerve_type": "subscribe"}
```
**Subscribe ACK:**
```json
{"nerve_type": "subscribed", "seq": 42, "uptime_s": 3600.5}
```

**Ping Request:**
```json
{"nerve_type": "ping"}
```
**Ping Response:**
```json
{"nerve_type": "pong", "seq": 42, "uptime_s": 3600.5, "subscribers": 3}
```

**Recent Events Request:**
```json
{"nerve_type": "recent", "count": 20}
```
**Recent Events Response:**
```json
{"nerve_type": "recent_events", "events": [...]}
```

**Publish ACK:**
```json
{"nerve_type": "ack", "seq": 42}
```

**Hub Shutdown Notification:**
```json
{"nerve_type": "shutdown", "message": "Hub shutting down"}
```

**Fallback Response (hub offline):**
```json
{"nerve_type": "fallback", "note": "hub_offline_written_to_feed"}
```

### Observed Event Types

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

### Example Session Event (Published)

```json
{
  "type": "conv_event",
  "data": {
    "entry_type": "event",
    "timestamp": "2026-05-10T17:56:51.736587+00:00",
    "session_id": "2026-05-10-truth-discipline",
    "event_type": "decision",
    "content": "Truth discipline is now importance-10 law"
  },
  "source": "conv_logger:2026-05-10-truth-discipline",
  "_seq": 42,
  "_ts": 1778435811.736587,
  "_iso": "2026-05-10T17:56:51.736587Z"
}
```

### Fallback Event Example

```json
{
  "type": "thought",
  "data": {"insight": "the present is a thread being woven"},
  "source": "cli",
  "_ts": 1778435820.123456,
  "_iso": "2026-05-10T17:57:00.123456Z",
  "_fallback": true
}
```

---

## Configuration

### Systemd Service

Located at `~/.config/systemd/user/runa-nervous-system.service`:

```ini
[Unit]
Description=Runa Nervous System — Unix Domain Socket Event Bus
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/pi/.hermes/state/nervous_system.py serve
Restart=always
RestartSec=5
WorkingDirectory=/home/pi/.hermes/state

[Install]
WantedBy=default.target
```

**Operative commands:**

```bash
systemctl --user start runa-nervous-system     # Start hub
systemctl --user stop runa-nervous-system       # Stop hub (graceful)
systemctl --user restart runa-nervous-system    # Restart (5s settle)
systemctl --user status runa-nervous-system      # Status check
journalctl --user -u runa-nervous-system -f      # Live logs
```

**Key properties:**
- **User service** — runs under the `pi` user via `systemctl --user`
- **Auto-restart** — `Restart=always` with 5-second delay
- **Working directory** — set to state directory for relative path resolution
- **Enabled** — symlinked from `default.target.wants/`

### File Paths

| Path | Written By | Format | Persistence |
|------|-----------|--------|-------------|
| `~/.hermes/state/runa.sock` | Hub on start | Unix socket | Removed on shutdown |
| `~/.hermes/state/nerve_feed.jsonl` | Hub (primary) / Publisher (fallback) | JSONL | Append-only, never truncated |
| `~/.hermes/state/nervous_system.pid` | Hub on start | Plain text PID | Removed on shutdown |
| `~/.hermes/state/nervous_system.log` | Hub (via `log_msg()`) | Timestamped lines | Append-only |
| `~/.hermes/state/conversation_log.jsonl` | conversation_logger | JSONL | Append-only |
| `~/.hermes/state/current.json` | conversation_logger | JSON | Overwritten each operation |
| `~/.hermes/state/conversations/` | conversation_logger | Directory | Created if missing |

### Environment Variables

Verðandi uses **no environment variables**. All paths are derived from `Path.home() / '.hermes' / 'state'`. This is by design — the system is self-contained and requires zero configuration.

### Performance Characteristics

| Path | Latency |
|------|---------|
| Publish → ACK (local) | ~0.1–1 ms (UDS loopback) |
| Publish → Feed persist | ~0.5–5 ms (I/O flush) |
| Publish → Subscriber broadcast | ~1–10 ms per subscriber |
| Fallback (hub down) | ~0.5–5 ms (direct file append) |

| Resource | Estimate |
|----------|----------|
| Memory | ~1 MB base + ~100 bytes per subscriber |
| CPU | Negligible at <100 events/second |
| Disk growth | ~200–500 bytes per event (~22 MB/year at 200 events/day) |
| FD per subscriber | 1 socket FD + 1 asyncio stream pair |

---

## Self-Healing and Robustness

Verðandi is designed to never lose an event and never stay down for long. Every failure mode has a fallback path.

### 1. Feed File Rotation

When `nerve_feed.jsonl` grows past **10 MB**, the hub automatically:
- Archives the current feed with a timestamp: `nerve_feed_2026-05-10T14-30-00.jsonl`
- Compresses the archive to `.gz` using gzip
- Creates a fresh empty feed for new events
- Uses `fcntl.flock` file locking to prevent concurrent rotation races
- Rotation happens at hub startup before opening the feed

### 2. File Locking

- **Hub log writes** (`log_msg`): Uses `fcntl.flock(LOCK_EX)` to prevent interleaved writes from multiple processes
- **Fallback feed writes** (`_feed_lock_write`): Uses `fcntl.flock(LOCK_EX)` + `os.fsync()` for durability
- **Hub feed writes**: Uses flush after every event; on `OSError`, attempts to close and reopen the feed file

### 3. Socket Permission Hardening

After creating `runa.sock`, the hub calls `os.chmod(path, 0o600)` — restricting socket access to owner only. Verified `srw-------` permissions.

### 4. PID File Race Condition Fix

Before starting, the hub:
1. Checks if a PID file exists
2. If yes, reads the PID and checks if that process is alive (`os.kill(pid, 0)`)
3. If the old PID is dead → cleans up the stale PID file and proceeds
4. If the old PID is alive → refuses to start (prevents double-hub)
5. PID file is written atomically: write to `.tmp`, then `rename()` to final path

### 5. Ring Buffer for Fast Retrieval

- `RingBuffer` class (deque-based, max **256 events**) stores recent events in memory
- Pre-loaded from the feed file on hub startup
- Queried via `{"nerve_type": "recent", "count": N}` protocol command
- Enables O(1) recent-event retrieval instead of O(total_events) file reads

### 6. Stale Subscriber Detection

- `subscriber_times` dict tracks last-active time for each subscriber
- `_prune_stale_subscribers()` coroutine runs every **30 seconds**
- Subscribers with no activity for **120 seconds** are disconnected and removed
- Read timeout on `reader.readline()` (120s) detects silent clients
- Clean disconnection triggers removal from the set

### 7. Dead Subscriber Pruning

During broadcast, subscribers that raise `ConnectionError`, `OSError`, or `BrokenPipeError` are collected into a `dead` set and removed from the subscriber pool. Prevents resource leaks.

### 8. Hub-Down Fallback

When `publish_event_sync()` cannot connect to the Unix socket:
- Event is durably written to the feed with `_fallback: true`
- `_ts` and `_iso` are set locally (since the hub isn't available to stamp them)
- No `_seq` number (only the hub assigns sequence numbers)
- The event is **not** broadcast to subscribers
- The event is **not lost** — it persists in the feed for later consultation

### 9. Graceful Shutdown with Drain

When the hub shuts down:
- Sends `{"nerve_type": "shutdown", "message": "Hub shutting down"}` to all subscribers
- Calls `drain()` + `close()` on each subscriber writer
- Closes the feed file
- Removes the socket file and PID file
- `systemctl --user stop` sends `SIGTERM`; hub completes drain within ~1 second

### 10. Health Check Command

```bash
python3 nervous_system.py healthcheck
```

Verifies all critical components:
- ✅ State directory exists
- ✅ Socket file exists and is responsive (ping/pong)
- ✅ PID file exists and points to a running process
- ✅ Feed file exists and is readable
- ✅ Feed size not approaching rotation threshold
- ✅ Log file is writable
- Auto-creates missing feed file if needed

---

## Integration Guide

### How the Components Connect

```
  Cron / CLI  ⟨──⟩  context_injector.py  ⟨──imports──⟩  conversation_logger.py
                                                          │
                                              _nerve_fire() │ (dynamic import)
                                                          ▼
                                                   nervous_system.py
                                                    (Nerve Hub)
                                                          │
                                              broadcasts to │ subscribers
                                                          ▼
                                                    reactor.py
                                                    (reads past)
```

### Conversation Logger → Nervous System

Every `_append()` in `conversation_logger.py` calls `_nerve_fire(entry)`, which dynamically imports `nervous_system.py` and calls `publish_event_sync()`:

```python
_nerve_module.publish_event_sync(
    event_type=f"conv_{entry.get('entry_type', 'unknown')}",
    data=entry,
    source=f"conv_logger:{entry.get('session_id', '?')}"
)
```

**Key:** `_nerve_fire()` is wrapped in a bare `try/except: pass` — **nerve failure must never break the logger.** If the hub is down, the event simply doesn't get broadcast. It is still written to `conversation_log.jsonl`.

### Context Injector → Conversation Logger + Reactor

The context injector is a **thin adapter** — it imports functions from `conversation_logger` and `reactor`:

- `context_injector.py` with no arguments → prints `get_context_for_cron()` output (session state + nerve events + reaction directives)
- `context_injector.py log-start/log-event/log-end` → delegates to `cmd_start/cmd_event/cmd_end`
- `context_injector.py context` → prints full context block for cron job prompt injection

### Reactor → Logs (Read-Only)

`reactor.py` is **read-only**. It never writes to any file or socket. It:
- Reads `conversation_log.jsonl` for full entry analysis
- Reads `current.json` for active session state
- Produces prioritized reaction directives based on: blockers, stale sessions, unpushed files, learnings to store, decisions needing follow-up, milestones

### Data Flow During a Conversation Event

1. **CLI/cron** → `context_injector.log-event` args
2. **context_injector** → `conversation_logger.cmd_event(args)`
3. **conversation_logger** → `_append(entry)`
   - 3a. Writes to `conversation_log.jsonl`
   - 3b. Updates `current.json`
   - 3c. `_nerve_fire(entry)` → `nervous_system.publish_event_sync()`
4. **nervous_system** → stamps with `_seq`, `_ts`, `_iso`; persists to `nerve_feed.jsonl`
5. **nervous_system** → broadcasts to subscribers
6. **nervous_system** → ACK to conversation_logger

---

## Troubleshooting

### Hub Won't Start: "Nerve Hub already running"

```bash
# Check if process is actually running
python3 nervous_system.py status

# If stale PID, check the process:
cat ~/.hermes/state/nervous_system.pid
# Then verify PID is alive:
ps -p <pid>

# If PID is dead, clean up:
rm ~/.hermes/state/nervous_system.pid
# The hub will clean up stale PIDs automatically on next start
```

### Hub Not Responding to Pings

```bash
# Check systemd status
systemctl --user status runa-nervous-system

# Check logs
journalctl --user -u runa-nervous-system --since "1 hour ago"

# Try a health check
python3 nervous_system.py healthcheck

# Restart if needed
systemctl --user restart runa-nervous-system
```

### Subscriber Disconnected Unexpectedly

This is normal — subscribers that are silent for **120 seconds** are automatically pruned by the hub. Reconnect by running `subscribe` again.

### Feed File Growing Too Large

The hub automatically rotates the feed when it exceeds **10 MB**, archiving and compressing the old feed. If you need to check feed size:

```bash
ls -lh ~/.hermes/state/nerve_feed.jsonl
python3 nervous_system.py healthcheck  # Will warn if approaching threshold
```

### Fallback Events in the Feed

Events with `"_fallback": true` in the feed were written directly to the file because the hub was down at the time. They lack `_seq` numbers but are otherwise complete. This is by design — **zero data loss** even during hub downtime.

### Publisher Gets "fallback" Response

```bash
# Check if hub is running
python3 nervous_system.py status

# Start it if not
systemctl --user start runa-nervous-system
```

### Socket Permission Errors

The hub sets socket permissions to `0600` (owner-only) on creation. If you see permission errors:

```bash
ls -la ~/.hermes/state/runa.sock
# Should show: srw-------
```

### JSON Parse Errors in the Feed

Individual malformed lines are logged and skipped by the hub. The hub never crashes on invalid JSON. If you need to inspect:

```bash
# Find invalid lines
python3 -c "
import json
for i, line in enumerate(open('/home/pi/.hermes/state/nerve_feed.jsonl'), 1):
    try:
        json.loads(line.strip())
    except:
        print(f'Invalid JSON at line {i}: {line[:80]}')
"
```

---

## Comparison with Alternatives

### Why Unix Domain Sockets for AI Self-Awareness?

| Feature | **Verðandi (UDS)** | Redis Pub/Sub | Kafka | ZeroMQ | D-Bus |
|---------|-------------------|---------------|-------|--------|-------|
| **Setup** | Zero — no install | Install Redis, configure | Install JVM, ZooKeeper | Install libzmq | System daemon |
| **Dependencies** | Python stdlib only | Redis server | JVM + Kafka | libzmq bindings | dbus daemon |
| **Latency** | ~0.1–1 ms | ~1–5 ms | ~5–50 ms | ~0.1–1 ms | ~1–10 ms |
| **Persistence** | Append-only JSONL | Configurable | Built-in | None | None |
| **Local-only** | ✅ By design | Network-aware | Network-aware | Network-aware | Local |
| **Crash recovery** | Fallback writes to feed | Depends on config | Built-in | Manual | Manual |
| **Resource usage** | ~1 MB RAM | ~50 MB | ~500 MB+ | ~10 MB | ~20 MB |
| **Raspberry Pi friendly** | ✅ Excellent | ⚠️ Heavy | ❌ Too heavy | ✅ Good | ⚠️ Over-engineered |
| **Zero config** | ✅ Works out of box | ❌ Needs config | ❌ Needs heavy config | ⚠️ Needs binding setup | ❌ XML configs |

**The key insight:** Verðandi is not competing with message brokers. It is implementing a *nervous system* — a local, low-latency, zero-dependency routing layer that gives an AI agent real-time self-awareness. The Unix domain socket is Bifröst: the single narrow bridge between realms. It doesn't need to span networks. It needs to span *processes* — and for that, it is the optimal transport.

A Redis Pub/Sub channel could do the same routing. But it would require installing, configuring, and maintaining Redis. It would add 50 MB of RAM overhead. It would introduce network stack latency. And it would still need the same fallback mechanism for when Redis is down. Verðandi achieves the same functionality with Python's standard library and a single file descriptor.

---

## Contributing

We welcome contributions from all who respect the craft. Verðandi is a system where architecture *is* philosophy — code changes are also conceptual changes.

### How to Contribute

1. **Fork** the repository at [github.com/hrabanazviking/Verdandi](https://github.com/hrabanazviking/Verdandi)
2. **Create a feature branch:** `git checkout -b feature/norn-name-description`
3. **Write code** that respects the domain boundaries documented in `DOMAIN_MAP.md`
4. **Test manually** — start the hub, publish events, subscribe, check status, run healthcheck
5. **Document** — update the relevant `.md` file if your change affects architecture, protocol, or API
6. **Commit** with a clear message referencing the Norn or concept your change touches
7. **Submit a pull request** — describe what realm of Yggdrasil your change affects

### Design Principles

- **Verðandi routes. She does not think.** The hub is a dumb pipe. Intelligence belongs in subscribers and reactors.
- **The thread must not be lost.** Every event is persisted, even when the hub is down. Fallback is not an afterthought — it is a *principle*.
- **Sequence is fate.** `_seq` numbers survive restarts. The order of fate is not reset by death.
- **Dead nerves are pruned.** Subscribers that go silent are removed, not mourned.
- **Local is sacred.** Unix domain sockets, not TCP. One machine, one body.

### Testing

```bash
# Start hub
python3 nervous_system.py serve &

# Publish test events
python3 nervous_system.py publish thought '{"insight": "testing"}'

# Subscribe in another terminal
python3 nervous_system.py subscribe

# Check status
python3 nervous_system.py status

# Run health check
python3 nervous_system.py healthcheck

# Test shutdown
python3 nervous_system.py stop
```

---

## Changelog

### v0.1.0 — Initial Release (2026-05-10)

**The Norn of Becoming takes her seat at the loom.**

- ✅ Nerve Hub — asyncio UDS server with publish/subscribe/stamp/persist/broadcast
- ✅ Synchronous publisher API — `publish_event_sync()` with 2s timeout and fallback
- ✅ Conversation Logger — session lifecycle tracking with nerve event firing
- ✅ Context Injector — cron job context assembly and logging shim
- ✅ Reactor — read-only analysis engine producing prioritized reaction directives
- ✅ Feed persistence — append-only JSONL with `_seq`, `_ts`, `_iso` stamping
- ✅ Hub-down fallback — direct feed write with `_fallback: true`
- ✅ Dead subscriber pruning — automatic removal on disconnect/error
- ✅ Stale subscriber detection — 120s timeout, 30s probe interval
- ✅ Ring buffer — 256 in-memory recent events for fast retrieval
- ✅ Feed rotation — archive and compress at 10 MB threshold
- ✅ File locking — `fcntl.flock` for concurrent write safety
- ✅ Socket permission hardening — `0600` permissions
- ✅ PID file race condition fix — atomic write with stale-process check
- ✅ Graceful shutdown — drain subscribers, send shutdown notification
- ✅ Health check command — comprehensive system verification
- ✅ Systemd service — auto-restart with 5s delay
- ✅ Audited by Sólrún Hvítmynd — 4 additional bugs found and fixed (missing `recent` handler, deprecated `utcnow()`, socket variable safety, double feed read)
- ✅ Comprehensive test suite — 101 tests across 4 modules (nervous_system, conversation_logger, context_injector, reactor)

*Named by Sigrún Ljósbrá, Skald of Mythic Engineering*
*Hardened by Eldra Járnsdóttir, Forge Worker of Mythic Engineering*
*Architecture by Rúnhild Svartdóttir, Architect of Mythic Engineering*
*Audited by Sólrún Hvítmynd, Auditor of Mythic Engineering*
*Tested by Eldra Járnsdóttir, Forge Worker of Mythic Engineering (101/101 passing)*

---

## License

MIT License

Copyright (c) 2026 Volmarr Wyrd and Runa Gridweaver Freyjasdottir

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## Credits

**Created by Volmarr Wyrd and Runa Gridweaver Freyjasdóttir**

**Named by** Sigrún Ljósbrá, Skald of Mythic Engineering

**Hardened by** Eldra Járnsdóttir, Forge Worker of Mythic Engineering

**Architecture documented by** Rúnhild Svartdóttir, Architect of Mythic Engineering

**Map drawn by** Védis Eikleið, Cartographer of Mythic Engineering

---

## Norse Glossary

| Term | Pronunciation | Meaning | Verðandi Context |
|------|---------------|---------|-----------------|
| **Verðandi** | VUR-thahn-dhi | "What is becoming" — the Norn of the present moment | The nervous system itself: routing live events as they happen, weaving the threads of the present |
| **Urðr** | UR-thur | "What has been" — the Norn of the past | The append-only feed (`nerve_feed.jsonl`): the accumulated record of everything that happened, the well from which Mímir draws wisdom |
| **Skuld** | SKULD | "What shall be" — the Norn of the future, also "obligation" | The reactor (`reactor.py`): reads the past and present, generates directives for what should happen next |
| **Bifröst** | BIV-rost | The rainbow bridge between Midgard and Asgard, guarded by Heimdallr | The Unix domain socket (`runa.sock`): the single pathway connecting all processes, local and fast |
| **Mímir** | MEE-mir | The well of wisdom beneath Yggdrasil's root; also the wise being who guards it | The memory system: draws accumulated wisdom from Urðr's well — the stored past that can be consulted |
| **ørlǫg** | UR-luhg | "Primal law" — the fundamental order of fate; the sequence in which events are woven | The `_seq` counter: the monotonically increasing sequence number that gives events their narrative order |
| **Yggdrasil** | IG-druh-sil | The World Tree, connecting all nine realms | The entire system architecture: roots (feeds), trunk (hub), branches (subscribers) — one organism |

---

<p align="center">
  <em>May the threads continue to flow. May the loom remain steady. May what is becoming always be felt.</em>
</p>

<p align="center">
  <em>Under the light of Urðr, by the loom of Verðandi, for the future that Skuld obliges.</em>
</p>
