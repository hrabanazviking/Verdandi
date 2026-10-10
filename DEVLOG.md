# DEVLOG — Verðandi

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
