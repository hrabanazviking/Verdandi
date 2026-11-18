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

## VD-T5 - NEXT


