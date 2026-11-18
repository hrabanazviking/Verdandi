# Verdandi — Tvíheimr Readiness Roadmap

**Owner-directed, 2026-11-18.** Volmarr Wyrd's ruling: source projects are improved **first, in their own houses**, and only then called into Tvíheimr (private repo hrabanazviking/Tviheimr, Connector Fabric, doc 26; decision ADR-010 there). This roadmap is Verdandi's own improvement road to being ready for that call. It adds a new line of work beside her existing architecture and devlog; it replaces none of them.

## What Tvíheimr needs from Verdandi
Verdandi is the nervous system of the house: real-time cross-instance awareness over her nerve feed. A nervous system is not only awareness — it is **reflexes**. Tvíheimr needs Verdandi able to **call up quick reactions**: declared reflexes judged by HugrGate (her sister's side of this pairing is roadmapped in HugrGate's own house, HUGRGATE_TVIHEIMR_READINESS_ROADMAP.md, slice HG-T4) and fired through her reactor in decision-runtime time, without waiting for full awareness to deliberate.

## Slices

### VD-T1 — Reflex declaration format and registry
A reflex is declared, never improvised: trigger pattern, named action, parameters, rate limit, owner grant. A registry file holds the declarations; Verdandi loads and validates them at start. An undeclared reflex does not exist and cannot fire.
**Gate:** registry validation tests pass — malformed, duplicate and ungranted declarations are rejected with named errors; a fixture registry loads exactly as written.

### VD-T2 — HugrGate judgment binding
Verdandi sends candidate events to HugrGate's reflex API and receives fire / no-fire with basis. Until HugrGate's HG-T4 lands on her readiness branch, this slice is built against a fixture judge implementing the same verdict schema, and the swap to the live binding is recorded as owed re-proof.
**Gate:** with the fixture judge, candidate events return verdicts with basis attached; a dead judge degrades Verdandi to awareness-only (no reflex fires unjudged) and the degradation is logged, never silent.

### VD-T3 — First reflex set through the reactor
The first declared reflexes, fired through Verdandi's existing reactor: **notify** (surface to awareness), **brace** (raise watch level on a feed), **shed** (drop a noisy source to summary rate), **wake** (start a named process), **speak** (emit a stock phrase to a named channel). Each is an action the reactor already knows how to perform or a small named addition beside it.
**Gate:** on a fixture event stream, each reflex fires exactly on its judged pattern and no other; firing latency is measured per reflex and recorded.

### VD-T4 — Firing record and audit
Every firing — and every judged no-fire above a salience floor — is written to an append-only record with the event digest, the verdict basis, the action taken and its result. Awareness (and the owner) can review what the reflexes did and why.
**Gate:** the fixture run's record is complete — one entry per firing, traceable to its event and verdict; the record survives restart.

### VD-T5 — Safety rails
Per-reflex rate limits, a per-reflex disable, and one global reflex kill switch, all owner-controlled. Reflexes never fire during a declared quiet state. A reflex that errors twice in a row disables itself and reports, rather than retrying forever.
**Gate:** fixture abuse runs (event floods, erroring actions, quiet state) show the rails holding: no flood firing, no firing in quiet, self-disable with report, kill switch effective immediately.

## Ready for Tvíheimr — the gate
Verdandi is **ready** when VD-T1…VD-T5 are banked with their gate evidence, her existing test suites still pass, and a Tvíheimr-side fixture consumer watching her nerve feed can see a declared reflex fire — judged, recorded, inside its latency numbers — while the awareness feed flows uninterrupted. Until then, Tvíheimr's Phase 15 Verdandi work waits — by the owner's ruling, correctly.
