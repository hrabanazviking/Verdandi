# Verðandi 2.0: HugrGate-Accelerated Reflexes, Metacognitive Observation and Optional Bifröst Second Brain Integration

**Date:** 2026-11-19  
**Repository:** `hrabanazviking/Verdandi`  
**Status:** Phased architecture **plus limited opt-in code slice** on this feature branch; broad observatory/production integration NOT implemented  
**Owner decisions:** Newer owner-approved architecture supersedes earlier contradictory design assumptions, without silently disabling existing functioning infrastructure  
**Canonical Second Brain architecture:** [Bifröst Three-Tier Memory](https://github.com/hrabanazviking/bifrost-viewer/blob/docs/second-brain-incremental-multimodal-gateway-2026-11-19/docs/roadmaps/SECOND_BRAIN_THREE_TIER_MEMORY_ARCHITECTURE_2026-11-19.md), [Git-like Immutable Archive](https://github.com/hrabanazviking/bifrost-viewer/blob/docs/second-brain-incremental-multimodal-gateway-2026-11-19/docs/roadmaps/SECOND_BRAIN_GITLIKE_JOURNALED_ARCHIVE_2026-11-19.md), [Yggdrasil 2.0 Cognitive Architecture](https://github.com/hrabanazviking/bifrost-viewer/blob/docs/second-brain-incremental-multimodal-gateway-2026-11-19/docs/roadmaps/YGGDRASIL_2_ESOTERIC_COGNITIVE_ARCHITECTURE_SECOND_BRAIN_2026-11-19.md).  
**HugrGate boundary:** [HugrGate Tvíheimr Readiness](https://github.com/hrabanazviking/RuneForgeAI-HugrGate/blob/main/HUGRGATE_TVIHEIMR_READINESS_ROADMAP.md), HG-T4 reflex API and optional local decision backend.

## 1. Critical finding: Verdandi already has a reflex integration and an event nervous system

Inspected repository paths:
- `nervous_system.py`: Unix domain socket event hub, publish/subscribe, feed persistence, fallback, ring buffer, and control messages. The event-transport contract is designed for millisecond-scale local delivery.
- `reflexes.py`: approved declaration registry, trigger/owner grant, stable action names/rates.
- `reflex_judgment.py`: `FixtureJudge`, `HugrGateJudge` HTTP adapter to future HG-T4, `JudgmentBinding` fail-closed awareness-only fallback.
- `reflex_reactor.py`: owner kill switch, quiet state, cooldown, disable, error self-disable and five declared actions.
- `reflex_record.py`: persistent firing/no-fire audit.
- `heartbeat/core.py` + `heartbeat/reactor.py`: health observations and actions; original reactor's default may actually act, not dry-run.
- `reactor.py`: summarizes session blockers, decisions, learnings, file changes and tasks.
- `heartbeat/sjalfrefi.py`: existing active automation including Git pushes, flag writes and subprocess actions, hence **not** safe to couple directly to Second Brain analysis without separate explicit owner grants.
- `VERDANDI_TVIHEIMR_READINESS_ROADMAP.md`: preexisting HG-T4 linkage and declared reflex safety milestones (VD-T1..VD-T5).

Do not claim HugrGate is missing: a *binding already exists*; what's missing for production is **verified compatible live HG-T4 API deployment, performance/quality measurements, modern observation/reaction semantics, and controlled integration with Bifröst**. Equally, do not assert a faster event-bus transport merely by adding a decision engine.

**Repo owner rule:** NEVER modify the root README.md unless explicitly asked. This roadmap and new code do not edit it.

## 2. Architectural mission: faster decisions, richer awareness, bounded actions

```text
Source events (Verdandi's original Unix socket or other approved adapter)
               |
      Transport-only fan-out, no LLM in hot path
               |
    Optional metadata-only fast selector
      /               |               \
  unremarkable     deterministic     ambiguous/meaningful
   no action       reflex trigger     event/window pattern
                     |                  |
             prefilter no-match         v
                 (zero RPC)      optional HugrGate judgment
                     |                  |
               declared match           v
                     |           Metacognitive Observer
                     +------------------+
                                        |
                                  Proposed responses
                               evidence / confidence
                                        |
                       owner-granted and judged reflex policy
                                        |
                          notify, inspect, defer, shed,
                           focus-suggestion or no action
                         (never unbounded autonomous writes)
```

- **The socket must stay fast**. Never synchronously call HugrGate or Gufo from `NerveHub.handle_client`, `publish_event_sync`, feed rotation or basic broadcasts. Downstream observers are separate optional subscribers or consumers.
- **HugrGate is a bounded decision tool**: deterministic rule first; optional local in-process classifier; selectively escalate to a small local model or stronger Gufo Z13 inference only when tested as useful. No default cloud fallback, no automatic success without response validation.
- **Verdandi is the present-tense observation and reaction coordinator**, not a second PostgreSQL/pgvector database and not an alternate memory archive. Metacognition means internally observing patterns, uncertainty, goals, decisions, effects and resource states; it is not proof of literal consciousness.
- **Yggdrasil 2.0 is the optional deep interpretive layer**. Verdandi can request reflective synthesis in particular Nine-World functions for a complex event; never require all Nine Worlds for each event.
- **Bifröst remains sole owner** of canonical immutable long-term knowledge, current medium-term focus, ephemeral short-term session content, source/folder provenance and owner-approved memory branch commits.

## 3. First code slice committed on this branch

### A. HugrGate fast deterministic prefilter (`reflex_judgment.py`)

- `JudgmentBinding(..., prefilter_unmatched=True)` is opt-in and uses the existing `_trigger_basis` declaration matching logic.
- For a declared nonmatch, return an ordinary no-fire `Verdict` without opening an HG-T4 connection or invoking a model. Every declared reflex still gets a result; a disabled reflex remains no-fire. Matching triggers still need a validated judge verdict.
- Expose counters `prefilter_count` and `judge_call_count` for performance measurement. A wrong/mismatched reflex ID from a judge is rejected and degrades to no-fire, not action.
- Default `prefilter_unmatched=False` preserves legacy third-party judge semantics until operator explicitly enables the safer deterministic-first pathway.
- This is an optimization **to judge-call volume** and network/model usage, not a measured improvement to local event-bus throughput.

### B. Optional metacognitive observer (`metacognitive_observer.py`)

- Volatile, bounded event-window observation detects **event-rate pressure**, **repeat loops**, **repeated failure trends**, **state transitions**, **slow-operation signals**, **explicit evidence conflicts** and **missing-evidence uncertainty**.
- Returns typed `Observation` objects with source ID, category, severity, event digest, reason, bounded count and **suggested** reaction only. No raw event payloads stored and no filesystem/network side effect.
- Optional HugrGate-style `judge(summary)` callable can *filter* proposed escalations using **only redacted metadata**, not raw chat content. Fail closed on malformed or unavailable judgment. This is an **adapter interface**, not proof that the installed HG-T4 or HugrGate server already implements this exact metadata schema.
- Per-source/category cooldown, max event queue, timestamp window and bounded snapshot prevent feedback loops and unbounded working-memory growth.
- `MetacognitiveObserver.clear()` explicitly drops working state; default has **no persistent events or session logs**.
- `ReflexReactor(..., observer=observer)` optionally evaluates observation proposals before ordinary reflex judgment. It keeps at most a bounded window of observation summaries. The observer **cannot trigger any action**; only a declared owner-granted reflex with a positive judge verdict can fire.

### C. Synthetic tests

`tests/test_metacognitive_observer.py` covers prefilter skip, opt-in behavior, mismatched verdict rejection, event surge, repeated failure, state changes, latency, uncertainty, privacy-minimized judge input, fail-closed judge, bounded expiration and non-executing suggestions. Tests are committed but require CI/local pytest run; no running production system was exercised.

## 4. Where the major future optimization can happen

**A. More selective HugrGate calls.** Today `JudgmentBinding.judge_event` iterates over *every* declared reflex for *each* event. With `N` reflexes and `E` events, there can be `N×E` judge calls in the worst case. Deterministic trigger rejection can avoid most remote calls when real streams are sparse relative to declared conditions.

**B. Indexed reflex routing.** Add a validated trigger-indexing system keyed by event kind/source/feature buckets, with careful fallback for wildcard and threshold declarations. Never skip a truly matching declaration. Batch judgments for the remaining candidates only when the HugrGate API supports a verified batch contract.

**C. Hot-path separation.** Keep instant transport publish/subscription separate from nonblocking background judgment. Use bounded queues, priority, cancellation, backpressure, coalescing low-salience repeated observations, dropped-event counters and telemetry. Critical events must not be silently discarded.

**D. Backend selection.** Route clear deterministic cases directly; ambiguous cases to local HugrGate classifier; expensive conceptual interpretation to independently hosted Gufo Z13 only if the actual installed model/API can do it and cost/quality benchmarks support the choice.

**E. Reactor costs.** Eliminate repeated log/file scans, duplicate warning evaluation and unnecessary rule checks when possible, but avoid changing the existing heartbeat default auto-actions without owner review.

**F. Meaningful metacognitive patterns.** Detect loops ("same error recurs after attempted fix"), ineffective actions, contradictions between observed state and claimed success, declining health, stale work, resource contention, unexpected focus shifts and context exhaustion. Recommend bounded actions rather than automatically rewriting code or starting perpetual loops.

**G. Accuracy and false positives.** Benchmark abstention and false-positive alert rates. The goal is *better responsiveness with less unnecessary computation*, not a sensational and unverified throughput multiplier.

## 5. Metacognitive observation contract

Proposed future versioned event envelope, not yet implemented:

```text
ObservedEvent {
  event_id, source_id, kind, occurred_at, received_at, source_seq,
  severity?, latency_ms?, queue_depth?, error_code?, memory_tier?,
  action_id?, result_state?, source_version_id?, graph_generation_id?,
  privacy_class, payload_digest, correlation_id?
}
MetaState {
  active_workstreams[], recent_transitions[], trend_estimates[],
  prediction_candidates[], contradictory_observations[],
  unresolved_incidents[], known_limitations[], current_focus_ids[],
  resource_budget, last_observation_at, uncertainty_flags[]
}
ReactionProposal {
  proposal_id, event_refs[], diagnosis, epistemic_label, severity,
  urgency, confidence_if_calibrated, expected_benefit, risk,
  target_module, named_action?, allowed_scope, expires_at,
  requires_owner_approval, evidence_refs[], provider_trace[]
}
```

**Observation stages:** receive → validate/time-order/dedupe → correlate by stable IDs → compare against baseline → detect drift or contradiction → decide if further cognition is justified → get bounded HugrGate judgment if necessary → propose a reversible response → observe the response's actual outcome and update future calibration.

**Preserve meaningful distinctions:**
- `observed`: source actually reported it.
- `inferred`: hypothesis from multiple observations, requires evidence.
- `predicted`: projected state with uncertainty, never certain fate.
- `proposed`: suggestion not executed.
- `authorized`: only an owner's explicit grant or existing permitted internal policy can change state.
- `executed`: an action occurred, with an ID/time.
- `verified`: independent postcondition check shows the effect.

A declaration can specify a safe allowed action and escalation budget. No event payload or HugrGate text may invent shell commands, arbitrary repo writes, public network calls, new permission scopes or a new autonomous worker. Continue honoring per-reflex rate caps, quiet state, global kill switch and failure disable.

## 6. Optional Bifröst Second Brain module

**Preferred integration:** install Verdandi as an optional G14-local event-observation *sidecar or library adapter*. Use a private Unix domain socket on the same G14 or a precisely scoped authenticated local bridge; do not expose raw UDS endpoints through a public Janitor proxy, and do not require the original Raspberry Pi/Hermes paths. Other devices and the Z13 can publish selected metadata through a separately authorized private connector (e.g., Tailscale), not direct untrusted raw feed injection.

### Events it could observe (metadata only by default)

- Ingest scan start/end, new/changed/duplicate/moved counts, individual job status **without raw document contents**.
- Derived image caption and multimodal embedding generation, current model identity and duration.
- Skein delta processing and graph-generation validation, failure/rollback notice.
- Skry query quality indicators, empty/low-confidence retrieval, repeated unanswered question.
- Medium-term focus changes, owner-approved study or research task progress.
- Long-term journal commit and branch-head changes, reconciliation warnings or evidence conflicts.
- Gufo inference queue depth, latency, overload, model errors, privacy boundary warnings and service health.
- Short-term context pressure and session expiry by **opaque ID and metrics only**, no transcripts.
- Optional Yggdrasil 2.0 metacognitive request state, selected worlds, results/review status.

### Useful reaction proposals

| Observation | Proposed action | Owner/security boundary |
| --- | --- | --- |
| Same incoming source hash | No model work; report duplicate handled | Ingest owns dedup |
| Changed file stuck in extraction | Notify/resume selected retry after backoff | Privileged Ingest service only |
| Repeated Gufo slowdowns | Reduce background concurrency, preserve interactive chat | Resource policy owner grants |
| Graph-generation validation failed | Retain last known-good graph and request review | Skein atomic publish contract |
| Source contradiction | Ask for more evidence or suggest a research investigation | Never invent immutable facts |
| Medium-focus drift | Suggest focus boost or project reminder | Only mutable focus, owner review |
| Short-term memory expired | Purge volatile buffer | No transcript persistence |
| Long-term branch discrepancy | Prepare historical comparison, notify before merge | No autonomous branch commit |
| Visual lore identity inconsistency | Surface canonical-trait review proposal | No unapproved identity rewrite |
| Repeated correction fails | Flag ineffective action loop and abstain | No infinite remediation |

**Three-tier preservation:** Urðr = immutable archived past Bifröst records, not Verdandi's ordinary unfiltered append-only event log; Verðandi = present active mutable focus and live observations; Skuld = bounded future possibilities and action proposals, not automatic fate claims. For Bifröst, the traditional Verdandi JSONL feed **must not persist raw short-term conversation content**. Use an isolated metadata-only stream with configurable rotation/retention and explicit payload allowlist, or no durable event feed. Distinguish append-only Bifröst accepted-history journal from Verdandi's operational telemetry.

**Read-only character gateway:** Janitor/SillyTavern characters may search the whole Bifröst brain without per-character collection tuning, but MUST NOT be able to invoke privileged Verdandi reflex actions. A read-only query may request non-sensitive observer state from a separate API view, with no raw internal paths/secrets or agent text.

**Optional and reversible:** The Second Brain remains usable if Verdandi/HugrGate/Gufo/Yggdrasil is disabled or offline. Integrate through documented, versioned contracts instead of forcing every project to embed Verdandi's daemon.

## 7. Implementation milestones and gates

### V2-0 Baseline and reality audit
- [ ] Run existing tests, identify live installed Verdandi/HugrGate versions and actual HG-T4 endpoint, benchmark event bus p50/p95 and source of latency. Verify original Tvíheimr VD-T1..VD-T5 gates with test evidence; do not rely only on an outdated README.
- [ ] Identify which heartbeat actions currently modify files/repositories or launch processes, and isolate them from new Second Brain integration by default.

### V2-1 Low-risk fast decision (first code slice committed here)
- [x] Add opt-in prefilter for nonmatching declared triggers, preserving legacy defaults and fail-closed judgment.
- [x] Add counters/test fixtures for number of judge calls avoided.
- [ ] Run pytest and benchmark synthetic and real representative event streams against actual HG-T4 endpoint. Confirm no matching reflex skipped.
- [ ] Investigate a constant-time candidate index for trigger subsets and batch verdict contract without losing wildcard/general trigger behavior.

### V2-2 Bounded metacognitive observation (first code slice committed here)
- [x] Add in-memory event-window observer, typed non-executing proposals, minimal summaries, optional judgment adapter, cooldown and clear.
- [x] Wire optional observer to reflex reactor, with fail-open *event observation* but fail-closed *action judgment*.
- [ ] Test sustained streams, out-of-order events, poison metadata, high-cardinality sources, cross-process restart, session isolation and privacy with real configured metrics.
- [ ] Add configurable policies for baseline learning, correlation IDs, source reliability and post-action outcome measurement with source evidence.

### V2-3 Harden live HugrGate and graduated actions
- [ ] Verify/refine HG-T4 protocol and schema with HugrGate project; versioned validation, request batch, health check, local-only/authenticated transport and timeouts.
- [ ] Add opt-in local in-process classifier binding where possible, avoiding HTTP for high-frequency decisions.
- [ ] Make reflex actions require explicit owner grants, risk categories, trigger thresholds, cooldown, global stop, quiet state, per-action postconditions and auto-stop on repeated failure.
- [ ] No arbitrary shell command strings, repo commits, file deletion, AI account actions, chat exfiltration or permanent Second Brain changes from untrusted events.
- [ ] Audit that a live judge cannot substitute reflex names or invent action parameters.

### V2-4 Second Brain adapter and three-tier semantics
- [ ] Publish/subscribe only metadata allowlisted events and map them to stable Bifröst source/graph/branch/focus IDs.
- [ ] Keep G14 canonical database and immutable archive unchanged; focus adjustments are reversible and owner-controlled.
- [ ] Enforce session-TTL and prevent raw short-term text from entering logs/backups. Test a distinctive sentinel string never appears after expiration.
- [ ] Keep universal character read-only access while not allowing a gateway token to trigger system operations.
- [ ] Run in observation-only shadow mode, prove useful event coverage/false-positive rate, then optional private local deployment.

### V2-5 Yggdrasil 2.0, Mímir and the Three Norns
- [ ] Send complex, *redacted* evidence patterns to the optional Nine-World cognitive orchestrator for interpretation, not every nerve event.
- [ ] Urðr/Helheimr analyze approved past commits, Verðandi observes current focus, Skuld suggests bounded hypotheses/scenarios, Niflheimr checks uncertainty, Mímir synthesizes reflective reports.
- [ ] Alternative knowledge branches are only proposals reviewed through Bifröst's existing Samverk-style immutable journal, never created automatically for short-lived chatter.
- [ ] Evaluate metacognitive utility, reasoning fidelity, resource cost, hallucination/false-positive rates and operator control.

### V2-6 Observability and acceptance
- [ ] Measure end-to-end event→proposal and event→authorized-action latency, p50/p95/p99, network and model calls avoided, misroute/no-fire false negatives, memory usage, source burst tolerance, rate-limited events, retries and timeouts.
- [ ] Measure observer precision, stale-alert rate, repeated-failure loops prevented, actionable suggestions accepted, impact on background GPU usage and quiet operating mode.
- [ ] Prove hub transport remains independent of HugrGate and Gufo; kill either and publish/subscribe still works.
- [ ] Benchmark G14 local decision vs private Z13 model escalation. **Never claim "vastly faster" without measured gains for particular workloads.**
- [ ] All existing Verdandi tests, Tvíheimr readiness gates, Bifröst archive safety tests and original application users must continue working after optional feature disabled.

## 8. Concrete performance experiment

Generate synthetic streams of 100, 10,000 and 100,000 events with varying fractions (1%, 10%, 50%) matching registered triggers. Compare:
1. Existing Verdandi reflex binding to the same fixture/real HugrGate adapter without prefilter.
2. New prefilter enabled, same trigger semantics and failure policy.
3. Later candidate-index/batch in-process HugrGate optimization.
4. New observer off vs on, with zero/rare/many proposal patterns.
5. Gufo model escalation for genuinely ambiguous cases, not every message.

Capture model calls avoided as `1 - actual_calls / baseline_calls` for comparable input. Record false-negative rate, action safety, p50/p95 judgment and overall publish-to-observe latency. Under mostly irrelevant event streams the prefilter could avoid many requests; it does **not** accelerate the fixed underlying model tokens/sec.

## 9. Documentation distribution and governance

- **Verdandi (this repo):** current code, owner-facing safety/runbook, metacognitive event model, HugrGate reflex binding, optional Second Brain adapter roadmap.
- **HugrGate:** HG-T4 and optional general metadata/decision backend contract, bounded confidence, local acceleration and test calibration.
- **Bifröst Viewer:** canonical Second Brain decision and three-tier/archive policy; add Verdandi as optional *observer and reaction proposal sidecar*, not a second canonical knowledge store.
- **Yggdrasil 2.0:** reflective cognitive function contracts and controlled escalation only when needed.
- Preserve all project README restrictions and licenses. No source files from the owner's private Second Brain or credentials enter public repositories.

**Closing principle:** *Verðandi carries the present; HugrGate decides what deserves a response; Yggdrasil may contemplate deeper meaning; Bifröst keeps the immutable record. No individual nerve impulse can rewrite the past.*
