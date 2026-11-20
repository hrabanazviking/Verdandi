# Verdandi Tviheimr Readiness - Progress Ledger

Branch: yrsa/tviheimr-readiness (off main @ faced525)
Method: Mythic Engineering roles run sequentially by keeper (no sub-agents on device).

## VD-T1 - Reflex declaration format and registry - BANKED
- reflexes.py: ReflexDeclaration + ReflexRegistry; named errors MalformedDeclarationError / DuplicateReflexError / UngrantedReflexError / UnknownReflexError.
- Fixture: tests/fixtures/reflex_registry_fixture.json loads exactly as written.
- Gate: pytest tests/test_reflex_registry.py -q -> 6 passed.
- Regression spot-check: tests/test_reactor.py + tests/test_nervous_system.py -> 66 passed (default TMPDIR; TMPDIR=~/forge-tmp breaks a unix-socket path-length test - pre-existing env quirk, unrelated).

## VD-T2 - HugrGate judgment binding - BANKED
- reflex_judgment.py: verdict schema {reflex, fire, basis, judge}; FixtureJudge (HG-T4 schema stand-in, trigger matching with per-condition basis); HugrGateJudge live client (swap-in, same schema); JudgmentBinding validates every verdict.
- Safety: dead / unreachable / malformed judge -> degraded awareness-only, no reflex fires unjudged, degradation logged (logging + degradation_log), never silent. Disabled reflexes return no-fire without judging; undeclared reflexes raise UnknownReflexError and are never judged.
- Gate: pytest tests/test_reflex_judgment.py -q -> 7 passed (with VD-T1: 13 passed combined).
- Regression spot-check: tests/test_reactor.py + tests/test_nervous_system.py -> 66 passed.
- OWED: live re-proof against HugrGate HG-T4 once it is banked on HugrGate's readiness branch (built against fixture judge per roadmap; do not block on sister project).

## VD-T3 - First reflex set through the reactor - BANKED
- reflex_reactor.py: ReflexReactor bound to JudgmentBinding; five actions notify/brace/shed/wake/speak with injectable handlers/starter (default wake records only, spawns nothing); unknown action rejected with UnknownActionError.
- Fixtures: tests/fixtures/reflex_first_set_fixture.json (5 declared reflexes) + reflex_event_stream_fixture.json (11 events: 5 matching, 6 non-matching).
- Gate: pytest tests/test_reflex_reactor.py -q -> 6 passed (with VD-T1+T2: 19 passed combined). Each reflex fires exactly once on its judged pattern and no other; effects verified (awareness/watch_levels/shed_sources/started/spoken); latency measured per reflex via perf_counter and recorded on each Firing (latency_ms).
- Regression spot-check: tests/test_reactor.py + tests/test_nervous_system.py -> 66 passed.

## VD-T4 - Firing record and audit - BANKED
- reflex_record.py: FiringRecord append-only JSONL (fsync per entry); event_digest = sha256 of canonical event JSON; entries carry seq/ts, kind, reflex, action, event, digest, verdict basis, judge, result/effect, latency_ms. record_no_fire records judged no-fires only at/above salience floor 0.5 (salience = max of salience/threat/noise). review()/firings()/for_reflex() for awareness/owner review.
- reflex_reactor.py: optional record= hook - firings and above-floor no-fires are written through the record; default (no record) behaviour unchanged.
- Gate: pytest tests/test_reflex_record.py -q -> 4 passed (with VD-T1..T3: 23 passed combined). Fixture run record complete: exactly 5 firing entries, each traceable to its event (digest recomputed) and verdict basis; record survives restart (new FiringRecord reads prior entries, appends continue seq, prefix unchanged).
- Regression spot-check: tests/test_reactor.py + tests/test_nervous_system.py -> 66 passed.

## VD-T5 - Safety rails - BANKED
- reflex_reactor.py: safety rails checked after judgment, before the action runs. Per-reflex rate limit from decl.rate_limit_per_minute (sliding 60s window, injectable clock); per-reflex owner disable/enable (disable_reflex/enable_reflex); one global kill switch (set_kill_switch, effective on the very next judged firing); declared quiet state (set_quiet, no firing in quiet); erroring action counted per reflex - a success resets the count, two consecutive errors self-disable the reflex and report (safety_reports + logging), the handler is not retried while disabled. Blocked firings are listed in reactor.blocked with their reason and are never executed or recorded as firings.
- Gate: pytest tests/test_reflex_safety.py -q -> 6 passed (flood: 10 events at limit 6 -> exactly 6 firings, 4 rate_limit blocks, firing resumes after the window; quiet blocks all and resumes; kill switch blocks immediately and resumes; per-reflex disable blocks only that reflex; erroring notify self-disables after 2 consecutive errors with reflex_error x2 + reflex_self_disabled reports, other reflexes still fire; single error then success does not disable). Reflex suite combined (VD-T1..T5 + ready gate): 30 passed.
- Regression spot-check: tests/test_reactor.py + tests/test_nervous_system.py -> 66 passed (96 passed combined with the reflex/ready suite).

## Ready for Tviheimr gate - PASSED (with one pre-existing env failure noted)
- Gate test: pytest tests/test_tviheimr_ready_gate.py -q -> 1 passed. A fixture consumer reading a nerve-feed JSONL line by line sees all 3 events in order (awareness feed uninterrupted) while the declared spike-notify reflex fires exactly once - judged (basis contains the trigger match), recorded in the FiringRecord with its latency_ms, inside its recorded latency numbers.
- Full suite: python3 -m pytest tests/ -q -> 1093 passed, 4 skipped, 1 failed in 159s. The single failure, tests/test_heartbeat_integration.py::TestCLIIntegration::test_pulse_command_exits_zero, is a pre-existing environment failure (heartbeat pulse needs a user systemd bus; auto_restart reports 2 services failed) - verified pre-existing by re-running it with the VD-T5 change stashed: it fails identically on the VD-T4 tree. It does not touch reflex code.
- OWED (unchanged): live re-proof of the VD-T2 binding against HugrGate HG-T4 once HG-T4 is banked on HugrGate's readiness branch.
- Roadmap VD-T1..VD-T5 complete. Verdandi is ready for Tviheimr by the roadmap's gate, subject to the owed live HG-T4 re-proof above.



## Correction 2026-11-20 - VD-T2 live re-proof DISCHARGED (mock-ruling fix)
- The owed live re-proof against HugrGate HG-T4 is done, against the REAL decision server (banked HugrGate code, started on an ephemeral localhost port with its HG-T6 judgment ledger on), over real HTTP. No fixture judge anywhere in the proof path.
- What had to be fixed first, in the open:
  1. reflex_judgment.py: the shipped HugrGateJudge spoke an assumed protocol ({reflex, trigger, action, event} -> single verdict) that the real HG-T4 server never implemented - pointed at the real server it could only degrade. Rewritten to HG-T4's real wire protocol: register each declaration (POST /reflexes; trigger translated to a pattern: feed->source, kind->kind, _gte/_lte/_gt/_lt -> where comparisons, other fields -> where equalities), then judge per event (POST /reflex/judge) and read back that reflex's verdict. A missing feed/kind rides under the reserved value verdandi.unspecified (documented adapter convention). If a response lacks the reflex's verdict (e.g. the server restarted), the client re-registers once and retries.
  2. HugrGate side (banked in HugrGate's own repo @ 772b0b6): the HG-T4 pattern language could not express Verdandi's declared conditions at all - where values may now be numeric comparison objects, and where-only patterns are valid declarations. See HugrGate's campaign ledger.
- Proof (tests/test_reflex_judgment_live.py, 2 passed): JudgmentBinding(HugrGateJudge) over the VD-T1 first set (5 reflexes) and the recorded 11-event nerve stream fired exactly the hand-derived table (spike-notify, threat-brace, noisy-shed, stalled-wake, alert-speak once each, on their events only); every verdict judge=hugrgate-live with a server basis; zero degradation; fire-for-fire agreement with the fixture oracle; the server ledger verified with all 265 returned verdicts recorded. Killing the real server mid-proof degrades the binding to awareness-only with the degradation logged - the safety rule holds against the real path.
- Gates after the fix: test_reflex_judgment.py 7 passed; test_reflex_judgment_live.py 2 passed; reflex registry/reactor/record/safety + ready-gate files 23 passed. The Ready gate's 'subject to the owed live HG-T4 re-proof' caveat is discharged.
