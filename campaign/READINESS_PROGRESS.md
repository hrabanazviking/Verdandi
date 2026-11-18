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

## VD-T4 - Firing record and audit - NEXT

## VD-T5 - pending
