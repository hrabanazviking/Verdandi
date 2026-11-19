# DEVLOG — Verðandi

## 2026-10-11 — Forge run verdandi-dawn-forge (04:32 EDT) — "The Unbroken Thread"

Third forge run (dawn slot is now the sole daily Verdandi forge — dusk slot
retired 2026-10-11 per the halved cadence). Theme: the system's inner state
never lies and never dies silently. Two read-only recon workers reproduced
23 defects with real runs against tmp dirs (a third worker's 12 findings for
autobiography/worlds/ttrpg/rituals arrived after carving — they seed the
next run); Sólrún consolidated to 20 slices, killing the stale-write race
slice (needs CAS, not safely fixable in one slice).

Baseline: 1001 passed / 4 skipped / 1 flaky (test_pulse_command_exits_zero —
environmental, fails 3/3 at the pre-forge baseline commit too).
Result: **1064 passed / 0 failed / 4 skipped** (+63 new tests; the same
pre-existing flake excluded).

### Nerve hub integrity (slices 3–5)
- `nervous_system.py`: a single frame bigger than the reader limit raised
  bare ValueError (3.12) → client got RST, no error frame. Now the hub
  drains the hostile frame, then answers the structured
  `{"nerve_type":"error","reason":"message_too_large"}` — no traceback, hub
  keeps serving. (The drain-first matters: closing with unread megabytes
  turns into an RST that eats the error frame.)
- Quiet subscribers (the documented `subscribe` use case) were booted after
  SUBSCRIBER_TIMEOUT_S of silence. The hub now proves liveness with a
  keepalive `ping` instead; a dead peer fails the write and is dropped.
  The `subscribe` CLI skips the new server ping as control chatter.
- `cmd_stop` sends SIGTERM for "graceful shutdown", but the default SIGTERM
  action killed the process before the drain path ran — subscribers never
  got the documented `shutdown` frame. serve() now routes SIGTERM into the
  shutdown event so the drain executes.

### Runa feeling, honestly wired (slices 1, 2, 9–11)
- `runa_mood_arousal_system.py`: `integrate_reward/negative_system` read
  stat keys the writers never emit — a silent no-op. Now reads the real
  `stats.total_rewards/total_negatives/total_intensity`, so mood actually
  reflects reward history. `load_state` survives non-dict/wrong-shaped JSON
  (loud warning, baselines); `save_state` is atomic.
- `runa_reward_system.py` / `runa_negative_system.py`: corrupt DBs crashed
  every entry point — now fall back to empty history LOUDLY and rewrite a
  valid DB; history lists capped at 500 (stats stay cumulative); saves are
  atomic. The dead nerve-emit path (`sys.path.insert(~/.hermes/state)`,
  where nervous_system can never exist) now resolves from the repo root —
  reward/negative events actually reach the nerve.
- `push_reward.py`: unknown tier raised bare KeyError — now ValueError
  naming the valid tiers.

### CLI honesty (slice 12)
- Six CLIs (`mood_work`, `wishlist`, `muse_aspects`, `morning_mirror`,
  `mythic_engineering`, `runa_mood_arousal_system`): domain errors escaped
  as tracebacks with exit 1. Now every invalid invocation exits 2 with a
  single-line human-readable stderr message.

### State honesty (slices 13–20)
- `muse_aspects.py` HugrMood: load is all-or-nothing (any bad field rejects
  the whole file loudly — no more silent partial merges); save() atomic.
  `GefanRewards.record`: `extra` may add namespaced fields but can no
  longer clobber core fields (trigger/ts) — forgery raises ValueError.
  `status()` skips malformed rows and reports the skipped counts.
- Corrupt state JSON is quarantined (`<name>.corrupt-<ts>`) with a loud
  stderr warning instead of being silently destroyed on next write:
  `mood_work`, `wishlist`, `self_recognition`, `mythic_engineering`.
- `mood_work`: finished-session rows are validated on read; malformed rows
  are skipped and counted (`correlate()["skipped_malformed"]`, CLI log
  notes it) instead of KeyError-killing the read path.
- `morning_mirror`: naive timestamps are assumed UTC (same contract as
  `probe_due`) — the 48h citation window no longer shifts with TZ;
  `gather()` filters the FULL log by window before capping (recent(20)
  first was silently dropping real in-window evidence).
- `self_recognition.set_anchors`: non-string anchors raise the module's own
  ValueError, never AttributeError.
- `mythic_engineering.audit`: a non-git repo dir now yields a labeled
  `unbroken_whole` violation — never again a vacuous "all Sacred Laws hold"
  for unversioned code.
- `MoodWork`/`Wishlist` honor `MUSE_ASPECTS_STATE_DIR` — no more split-brain
  with the mood file MuseAspects/MorningMirror read.

### Incidents
- VM RAM pressure critical this run (95–97% used, ~250–500MB available;
  no swap). Full suite still completed in ~95s. No OOM.
- No external hard-reset actor observed this run — all commits persisted.

## 2026-10-10 — Forge run verdandi-dusk-forge (16:32 EDT) — "The Kept Oath"

Second forge run. Theme: the system's inner promises kept true. Dawn run
hardened the outer nerve (hub, bridges, env-decoupled tests); dusk run
audits the inner organs — memory, judgment, healing, prediction, truth —
with 23 bugs confirmed by reproduction, consolidated by Sólrún to 20 slices.

Baseline: 889 passed / 4 skipped / 0 failed.

### Heartbeat honesty (slices 1–8)
- `heartbeat/actions/eir_action.py`: `_heal_database` DESTROYED the DB it
  "healed" — never ATTACHed the backup, swallowed OperationalError, committed
  an empty DB, deleted the backup, returned True. Rewritten: ATTACH backup,
  copy DDL + rows, rebuild indexes, verify integrity_check + per-table row
  counts; backup kept until verification passes; False + loud ERROR log on
  any failure.
- `heartbeat/actions/vor_action.py`: VörAction overrode BaseAction.execute,
  losing exception guards; the no-action branch referenced nonexistent
  `ActionSeverity.INFO` → AttributeError killed core.pulse() via
  Reactor.react. Fixed: renamed to `_execute` (BaseAction guards restored),
  INFO → SKIPPED, `action_name=` field fixed, isinstance guards on capacity
  "status"-string entries (dawn :69 fix pattern).
- `heartbeat/checks/urdr.py`: `_check_systemd` substring `"active" in
  stdout` matched `Active: inactive (dead)` → dead services reported ACTIVE
  and Gungnir skipped restarts. Real `Active:` state-word parse now.
  `_check_cron` dropped @-spec jobs (@reboot/@daily/@hourly); recognized now.
- `heartbeat/checks/skuld.py`: `_predict_capacity` was permanently dead —
  read `health.get("disk_used_percent")` on the outer dict while Eir nests
  metrics under `["health"]["details"]`, and looked for
  `memory_used_percent` while Eir writes `ram_used_percent`. Both fixed;
  Vör's pre-emptive healing can now actually trigger.
- `heartbeat/core.py`: overnight maintenance windows (22:00–02:00) never
  fired on "HH:MM" string compare — wrap-midnight logic added. Zero enabled
  checks no longer report perfect health: new `DaemonState.UNKNOWN`,
  HealthScore returns None / no_checks marker, `last_healthy_pulse` not
  stamped on empty. Pulse path also feeds circuit-breaker states to the
  prometheus gauge (S8 hook).
- `heartbeat/reactor.py`: default DISCIPLINE rule targeted unregistered
  `discipline_enforcement` — every pulse logged "not found" and skipped.
  HeimdallAction (the real implementation) now registered under that name.
- `heartbeat/prometheus.py`: `verdandi_circuit_breaker_state` and
  `verdandi_prediction_days_to_exhaustion` were registered but never set —
  both now populated in `update_from_state()`.

### Memory integrity (slices 9–15)
- `conversation_logger.py`: all 5 current.json write sites now atomic
  (tmp + fsync + os.replace). Corrupt/truncated/wrong-type current.json is
  LOUD: stderr warning + backup to `current.json.corrupt.<ts>`, never silent
  state loss. `cmd_show`/`cmd_recent`/`get_context_for_cron` coerce
  non-string content instead of crashing. `test_get_current_state_corrupt_file`
  updated to the new honest contract.
- `context_injector.py`: repo-local dir now precedes `~/.hermes/state` on
  sys.path — a deployed conversation_logger copy can no longer shadow the
  repo file; state dir stays as fallback only.
- `reactor.py`: naive (tz-less) timestamps assumed UTC instead of killing
  react() with TypeError; non-dict JSONL lines skipped loudly instead of
  AttributeError; re-occurring blockers re-activate with a reoccurrence
  count (regressions visible, not silent); dead `react(focus=...)` / `--focus`
  flag now genuinely filters (all/blockers/learnings/files/next).

### Truth integrity (slices 16–20)
- `reality_audit.py`: slice-8 findings now carry the standard
  `check`/`detail` keys (were crashing `run_audit()` and `worlds audit` with
  KeyError); one torn autobiography chapter line no longer aborts the whole
  audit — skipped loudly, counted, scanning continues.
- `weekly_saga.py`: `gather()` read `autobiography.jsonl` (never exists) —
  now reads `autobiography_chapters.jsonl`, so the digest sees real chapters.
- `joy_ledger.py`: non-dict JSONL rows skipped loudly instead of crashing
  `audit()`/`delights()` with TypeError/AttributeError.
- `verdandi/eir/layers.py`: `load_profiles_from_yaml` degrades per-layer on
  malformed config (null mappings, non-dict effort_levels) instead of dying.
- `shadow_arcs.py`: `arcs(status="reopened")` can never match by status
  string — now matches arcs with a reopen event in history / reopen_count.

### Incidents
- None from the external hard-reset actor this run — all worker edits
  persisted; no re-application needed. (Dawn run saw two resets.)
- Cross-worker test pollution observed twice in full-suite runs (S2's
  dry_run=False rule test briefly fired a real disk cleanup; the S6 test
  rewrite of `test_no_checks_preserves_state`); each was isolated and the
  final full suite is green. No user data harmed.
- My own acceptance brief for S3 miscounted expected cron jobs (said 3,
  correct is 4) — the worker's assertion of 4 was right.

## 2026-10-10 — Forge run verdandi-dawn-forge (04:32 EDT) — "The Green Forge"

First forge run for this repo. Theme: make the suite truly green in ANY
checkout (env-decoupled), then harden the nerve hub, bridges, and WYRD
mirror stack: input validation, broadcast backpressure, graceful
degradation, self-healing, timezone-consistent design.

Baseline: 825 passed / 35 failed (all environmental) / 1 skipped.
Result: **889 passed / 0 failed / 4 skipped.**

### Env decoupling (slices 1–6)
- `tests/test_nervous_system.py`: removed all `@pytest.mark.asyncio`;
  async hub tests wrapped in sync `asyncio.run()` shims. Zero
  `pytest.mark.asyncio` occurrences remain repo-wide.
- `tests/test_heartbeat_integration.py`: repo root now derived from
  `__file__` with `VERDANDI_REPO` env override (was hardcoded
  `~/Verdandi`).
- `wyrd_bridge.py`: `_load_wyrdforge()` raises typed
  `WyrdUnavailableError(ImportError)` naming the expected repo path;
  honors a pre-loaded `sys.modules` double. `wyrd_inbound.py` gained
  `wyrdforge_available()` and degrades gracefully (None/[], no crash).
- `tests/test_wyrd_waveb.py` (17) + `tests/test_wyrd_bridge.py` (5):
  integration tests skip with reason "WYRD repo absent" when wyrdforge
  is unimportable; a fake `wyrdforge` module fixture in `sys.modules`
  unit-tests the decoupled logic (ID stability, mapping, supersedes
  chains, transitions, reflection dedup, cursor, registry flip) —
  22 pass via the fake.
- `verdandi/eir/layers.py`: `load_profiles_from_yaml` guards with
  `path.is_file()` (a directory path warns + returns {} instead of
  raising IsADirectoryError).
- `test_mythic_engineering.py::test_doctrine_reads_his_real_codex`:
  skips with reason when the personal codex is absent; passes against a
  tmp codex fixture.
- Fixed a real pre-existing bug surfaced by the CLI tests:
  `heartbeat/actions/vor_action.py:69` crashed with
  `AttributeError: 'str' object has no attribute 'get'` when skuld's
  capacity map carried status strings; now skips non-dict predictions
  (same guard skuld.py itself uses).

### Nerve hub hardening (slices 7–12, 16, 17)
- `handle_client`: max message size 1 MiB — oversized frames get a
  structured `{"nerve_type":"error","reason":"message_too_large"}` reply
  and the connection closes; hub keeps serving. Server StreamReader
  limit raised so the size check sees large frames before
  LimitOverrunError kills the handler.
- Broadcast backpressure: per-subscriber drain wrapped in
  `asyncio.wait_for` (5s); a stalled subscriber is dropped + pruned,
  healthy subscribers still receive.
- Malformed JSON frames: structured
  `{"nerve_type":"error","reason":"invalid_json"}` reply; connection
  loop stays alive.
- Feed write atomicity: `_feed_lock_write` uses `os.fdatasync` with
  `os.fsync` fallback.
- `subscribe` validation: only known fields accepted; unknown fields or
  non-dict frames get structured errors, never KeyError/AttributeError.
- Restart dedup (Sólrún rule): bug did NOT reproduce — subscribers only
  receive live publishes; restart replays the feed into the ring buffer
  only. Converted to a verified regression test asserting no duplicates
  (`_seq == [4,5]`, unique) across restart.
- `cmd_healthcheck()` now returns a structured dict including
  `socket_ok` (real connect + ping/pong) and `feed_writable` (append +
  zero-byte write test); print output unchanged.
- `get_status()` now includes `subscriber_count` and `uptime_s`
  (feed_size_bytes kept).

### Bridges + WYRD mirror (slices 13–15, 18, 19)
- Timezone audit: zero `datetime.utcnow()` calls in non-test source;
  `_utcnow()` helpers verified tz-aware. New
  `tests/test_timezone_consistency.py` asserts this permanently and that
  emitted timestamps parse as tz-aware. (Naive `log_msg` timestamp in
  `nervous_system.py` converted to `datetime.now(timezone.utc)`.)
- `telegram_bridge.py`: bounded retry with exponential backoff + jitter
  (`SEND_MAX_RETRIES=5`, base 1s, cap 60s) around the transport; after
  exhaustion a `telegram_bridge_transport_failed` event is published to
  the nerve feed. New `send_message(chat_id, text)` outbound path with
  the same auth pattern as `fetch_updates`. All messages truncated to
  Telegram's 4096-char limit with `… [truncated]` marker.
- `wyrd_ledger_append.py`: verified idempotent across re-runs and state
  resets (state watermark + ledger-text subject check); added
  `test_double_append_is_idempotent`. Fixed a real crash: `_load_state`
  raised `AttributeError` on valid-JSON-wrong-shape state files; now
  degrades to fresh state. Corrupt JSONL lines were already skipped
  loudly; test added covering corrupt feed lines, garbage/wrong-shape
  state.

### Incidents
- Twice during the run, uncommitted worker edits were reverted by an
  external actor (reflog showed hard resets to HEAD); workers detected
  and re-applied their changes. A root-owned `/nonexistent/path`
  directory was created at 08:36 UTC by an unknown external process —
  flagged for Volmarr to inspect.
