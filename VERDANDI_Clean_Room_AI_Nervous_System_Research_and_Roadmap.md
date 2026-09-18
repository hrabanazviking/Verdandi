# VERÐANDI Clean-Room Research & Evolution Roadmap
## Comparative Study of Emerging AI “Nervous System” Architectures

**Project:** VERÐANDI — AI Nervous System / Real-Time Event Bus / Heartbeat  
**Prepared for:** Volmarr Wyrd / RuneForgeAI  
**Research snapshot:** 2026-09-17  
**Document type:** Clean-room architectural research + independent implementation roadmap  
**Status:** Research specification. No external source code is reproduced or required.

---

# 0. Executive Summary

VERÐANDI is already a real, functioning AI nervous-system architecture rather than a speculative diagram.

Its existing public architecture includes:

- a local low-latency Unix-domain-socket event bus;
- append-only event persistence;
- process-to-process publish/subscribe;
- heartbeat-driven autonomous self-monitoring;
- state-machine awareness;
- circuit breakers;
- health scoring and trend detection;
- predictive health analysis;
- pre-emptive healing;
- action/reaction rules;
- local SQLite persistence;
- Prometheus metrics;
- graceful degradation;
- self-healing;
- project, memory, schedule, and system-health sensing.

That gives VERÐANDI a particularly strong **peripheral nervous system + autonomic nervous system** foundation.

Several other 2026 projects independently explore neighboring parts of the same design space:

1. **Pulse / Iris** explores drives, salience, attention, persistent emotional state, autonomous initiative, learned weights, instincts, identity bundles, and multi-agent coordination.
2. **Kit Daemon** explores multiple asynchronous background loops, proactive research, skill evolution, local inference, self-diagnosis, auto-repair, and autonomous worker behavior.
3. **Connector OS** explores control theory, homeostasis, thresholds, hysteresis, multimodal sensing, external constraints, human-state modeling, and regulated actuation.
4. **SPINE** explores agent-native communication protocols, capability discovery, distributed coordination, semantic addressing, persistent distributed memory, tracing, stream flow-control, and swarm-oriented infrastructure.

The strongest next step is **not** to turn VERÐANDI into a clone of any one project.

Instead:

> **Keep VERÐANDI as the small, fast, dependable nerve substrate, then add optional higher-order layers around it.**

The proposed target architecture becomes:

```text
                     ┌───────────────────────────────┐
                     │        COGNITIVE MODELS       │
                     │ LLMs · planners · specialists │
                     └───────────────┬───────────────┘
                                     │
                         ┌───────────▼───────────┐
                         │  HUGINN / CORTEX LAYER│
                         │ reasoning orchestration│
                         └───────────┬───────────┘
                                     │
              ┌──────────────────────▼─────────────────────┐
              │            VERÐANDI HIGHER BRAIN           │
              │ drives · salience · attention · identity   │
              │ learning · goals · instincts · inhibition  │
              └──────────────────────┬─────────────────────┘
                                     │
              ┌──────────────────────▼─────────────────────┐
              │          HJARTSLÁTTUR AUTONOMIC CORE       │
              │ heartbeat · health · prediction · healing  │
              │ thresholds · state machine · breakers      │
              └──────────────────────┬─────────────────────┘
                                     │
              ┌──────────────────────▼─────────────────────┐
              │              VERÐANDI NERVE HUB            │
              │ event routing · sequencing · pub/sub       │
              │ append-only feed · local persistence       │
              └──────────────────────┬─────────────────────┘
                                     │
       ┌─────────────────────────────┼─────────────────────────────┐
       │                             │                             │
┌──────▼──────┐               ┌──────▼──────┐               ┌──────▼──────┐
│   SENSORS   │               │   MEMORY    │               │  ACTUATORS  │
│ system/git  │               │ episodic    │               │ tools       │
│ files/web   │               │ semantic    │               │ services    │
│ users/time  │               │ working     │               │ messages    │
└─────────────┘               └─────────────┘               └─────────────┘
```

The roadmap in this document preserves four principles:

1. **Local-first.**
2. **Pi-friendly.**
3. **Model-agnostic.**
4. **The nerve hub stays simple.**

The result is not “one huge AGI program.”

It is an extensible digital nervous system in which increasingly sophisticated organs can be attached without corrupting the nerve itself.

---

# 1. Clean-Room Research Rules

This document deliberately uses a clean-room architectural methodology.

## 1.1 Allowed research inputs

Research is limited to:

- public READMEs;
- architecture descriptions;
- public whitepapers;
- public feature lists;
- public roadmaps;
- published documentation;
- public statements of behavior;
- VERÐANDI’s own repository and documentation.

No implementation from another project is required for this roadmap.

## 1.2 Explicitly excluded

This document does **not** reproduce:

- external source-code functions;
- proprietary algorithms;
- copied class structures;
- copied implementation logic;
- copied test suites;
- copied prompt libraries;
- copied configuration files;
- copied internal schemas.

Where another project demonstrates a useful architectural pattern, this document restates only the **problem being solved** and independently designs a VERÐANDI-native solution.

## 1.3 Clean-room translation pattern

For every outside idea:

```text
OBSERVE:
What general capability exists?

ABSTRACT:
What problem does that capability solve?

RE-DESIGN:
How would VERÐANDI solve that problem from its own architecture?

IMPLEMENT:
Write new code against VERÐANDI's own interfaces and tests.
```

Example:

```text
Observed capability:
A system accumulates motivational pressure.

Abstract requirement:
An autonomous agent needs changing internal priorities over time.

VERÐANDI-native solution:
Create a generic Drive Registry whose values are updated from nerve events,
time, goals, health, memory and feedback.

No external implementation is copied.
```

---

# 2. VERÐANDI Baseline

Source repository:

- https://github.com/hrabanazviking/Verdandi

The current public VERÐANDI design already contains a surprisingly large fraction of what newer “AI nervous system” projects are attempting.

## 2.1 Core nerve

VERÐANDI’s original nerve layer provides:

- Unix domain socket transport;
- real-time local pub/sub;
- monotonic sequence numbering;
- timestamps;
- append-only JSONL persistence;
- fast recent-event ring buffer;
- direct-to-feed fallback when the hub is unavailable;
- subscriber pruning;
- graceful shutdown;
- feed rotation;
- filesystem-based isolation;
- synchronous publishing API.

This should remain the **sacred small core**.

Do not casually inject cognition into the nerve hub.

Its value comes from being understandable, boring, deterministic, and dependable.

## 2.2 Hjartsláttur

The heartbeat subsystem already adds:

- autonomous periodic execution;
- configurable jitter;
- system-health checks;
- project-state checks;
- memory-health checks;
- schedule awareness;
- action registry;
- reactor rules;
- state machine;
- circuit breakers;
- health scoring;
- predictive health trends;
- anomaly detection;
- capacity prediction;
- maintenance windows;
- metrics;
- pre-emptive healing.

This is already recognizably analogous to an **autonomic nervous system**.

## 2.3 Existing philosophical split

VERÐANDI’s own design principle is important:

> **VERÐANDI routes. It does not think.**

That principle should survive future development.

Higher cognition should be implemented as subscribers, processors, regulators, and optional services.

The nerve should remain the nerve.

---

# 3. Comparative Project Research

---

# 3.1 Pulse / Iris

Public sources:

- https://github.com/Hypostas/pulse
- https://github.com/Hypostas/pulse/blob/main/NERVOUS-SYSTEM.md

Observed public framing:

> Autonomous cognition engine / nervous system for AI agents.

Publicly described capabilities include:

- persistent drive state;
- six broad motivational categories;
- urgency accumulation;
- autonomous wake-up;
- sensory inputs;
- salience filtering;
- persistent emotional variables;
- attention mechanisms;
- self-awareness metadata;
- persistent memory;
- autonomous skills or “instincts”;
- deterministic behavior before model invocation;
- learned adaptive weights;
- metrics/dashboard;
- multi-agent peer synchronization;
- identity export/import;
- local-model evaluation options;
- continuous daemon operation.

## 3.1.1 Most valuable ideas for VERÐANDI

### A. Drives

VERÐANDI currently knows **what is happening** and **how healthy it is**.

Drives add:

> **What currently matters enough to deserve action?**

Possible independent VERÐANDI drives:

- goal pressure;
- curiosity;
- maintenance;
- social;
- learning;
- unfinished-task pressure;
- memory housekeeping;
- project-health pressure;
- exploration;
- user-request debt.

A drive should be just state, not personhood magic.

Each drive can have:

```text
current value
baseline
decay rate
growth rate
weight
trigger threshold
cooldown
evidence
last updated
```

### B. Salience

Every nerve event should optionally carry a normalized importance estimate.

Proposed independent field:

```json
{
  "_salience": 0.74
}
```

This allows downstream components to avoid treating:

```text
temperature changed by 0.1°C
```

as equally important as:

```text
memory database failed integrity check
```

The hub itself should **not calculate salience**.

Publishers may supply it. A dedicated salience subscriber may enrich events.

### C. Attention

Attention is not the same as salience.

Salience asks:

> How important is this event?

Attention asks:

> Which of all currently important things gets limited cognitive resources now?

A future VERÐANDI attention scheduler could combine:

```text
salience
urgency
drive pressure
recency
goal relevance
human priority
resource cost
risk
cooldown
```

### D. Instincts

An “instinct” can be implemented independently as:

> A small deterministic reaction package that executes without invoking an LLM.

Examples:

- rotate logs;
- repair an index;
- commit a known-safe state file;
- notify about overheating;
- refresh a stale cache;
- summarize a queue;
- check an upcoming deadline.

This is excellent for Pi efficiency.

Use deterministic code for predictable reflexes.

Use models only when interpretation or generation is needed.

### E. Identity bundle

A portable identity/state bundle is useful for:

- migration between machines;
- backup;
- agent continuity;
- cloning a test instance;
- disaster recovery.

VERÐANDI should eventually support a signed export containing:

```text
identity metadata
preferences
drive parameters
learned weights
goal state
memory references
capability declarations
configuration version
schema version
```

Secrets must **not** be included by default.

---

# 3.2 Kit Daemon

Public source:

- https://github.com/Kadatha/Kit-Daemon

Observed public framing:

> Self-improving, always-on AI nervous system for local assistants.

Publicly described capabilities include:

- multiple concurrent asynchronous loops;
- self-diagnosis;
- automatic service repair;
- proactive behavior;
- local inference;
- autonomous work;
- curiosity/research behavior;
- skill evolution;
- system monitoring;
- learning from interaction traces;
- specialist sub-agents;
- efficiency metrics;
- multi-device state synchronization.

## 3.2.1 Most valuable ideas for VERÐANDI

### A. Multiple independent rhythms

VERÐANDI currently has a central heartbeat.

A biological body does not run everything at one frequency.

Different loops should eventually run at different timescales.

Example:

```text
FAST LOOP         1–5 sec
socket health, urgent queue, service death

NORMAL LOOP       30–60 sec
CPU/RAM/temp, user activity, process state

COGNITIVE LOOP    5–15 min
goals, curiosity, unfinished tasks, opportunity detection

MAINTENANCE LOOP  hourly
memory cleanup, cache/index health

CONSOLIDATION     daily
summaries, memory compression, learning-weight update

DEEP MAINTENANCE  weekly
integrity audit, backups, archive rotation, benchmarks
```

This is preferable to one giant “pulse” doing everything.

### B. Loop supervision

Every loop should itself be observable.

Each loop publishes:

```text
loop.started
loop.completed
loop.failed
loop.overrun
loop.skipped
```

with:

```text
duration
next run
error count
resource cost
```

Then VERÐANDI can watch its own nervous-system processes.

### C. Resource-aware cognition

A Pi or laptop should not invoke an LLM merely because “something happened.”

A resource governor should consider:

```text
CPU load
RAM
GPU/VRAM
battery
thermal state
network availability
model availability
current human interaction
task urgency
```

before waking cognition.

### D. Autonomous worker queue

VERÐANDI could expose a job queue separate from the nerve feed.

The nerve says:

> Something happened.

The work queue says:

> This needs deliberate execution.

Keep those concepts distinct.

Suggested job states:

```text
queued
claimed
running
blocked
completed
failed
cancelled
expired
```

### E. Trace-driven improvement

Instead of allowing unrestricted self-modification, use:

```text
observe traces
identify recurring failure
propose change
test in sandbox
evaluate
require policy approval
promote
```

This keeps “self-improvement” measurable rather than mystical.

---

# 3.3 Connector OS

Public source:

- https://github.com/leenathomas01/connector-os

Published architecture: February 2026.

Observed public framing:

> A control-theoretic architecture adding regulation, state awareness, sensory feedback, thresholds, and stability to AI systems.

Key public ideas include:

- sensors;
- signal normalization;
- thresholds;
- hysteresis;
- explicit control laws;
- adaptive routing;
- human-state loops;
- actuator layers;
- infrastructure constraint ingestion;
- authority regulation;
- degraded modes;
- re-anchoring/recovery;
- one-way propagation of hard physical constraints.

## 3.3.1 Most valuable ideas for VERÐANDI

Connector OS is especially useful because it introduces something AI architectures often lack:

> **Control theory.**

VERÐANDI already has pieces of this, particularly circuit breakers and health-state hysteresis.

The opportunity is to generalize it.

### A. Explicit homeostasis

Define target operating bands for important state variables.

Examples:

```text
CPU temperature
memory pressure
event rate
LLM invocation frequency
task backlog
error frequency
latency
battery
network usage
human interaction load
```

Each variable can define:

```text
desired range
warning range
critical range
recovery threshold
minimum recovery duration
```

### B. Hysteresis everywhere it matters

Without hysteresis:

```text
healthy
warning
healthy
warning
healthy
warning
```

can oscillate around one threshold.

Instead:

```text
enter WARNING at 80
return to OK only below 70
```

This should become a generic VERÐANDI primitive rather than hand-written logic scattered across modules.

### C. Constraint hierarchy

Some signals should be advisory.

Others should be absolute.

Example:

```text
HARD CONSTRAINT
battery emergency
thermal shutdown
filesystem read-only
security lockout

SOFT CONSTRAINT
user may be busy
network slightly slow
goal can wait
```

The architecture should guarantee that hard constraints override drive pressure.

### D. Authority levels

Actions should carry authority classifications:

```text
LEVEL 0  observe only
LEVEL 1  recommend
LEVEL 2  safe local reversible action
LEVEL 3  consequential action requiring approval/policy
LEVEL 4  forbidden without explicit human authorization
```

This creates an architectural distinction between intelligence and permission.

### E. Recovery as a trajectory

Do not immediately return from CRITICAL to normal behavior after one good pulse.

Use a recovery phase:

```text
CRITICAL
   ↓
RECOVERING
   ↓
STABLE-PROBATION
   ↓
RUNNING
```

VERÐANDI already has RECOVERING.

Add explicit minimum stability windows to make it stronger.

---

# 3.4 SPINE

Public source:

- https://github.com/nervosys/SPINE

Observed public framing:

> Agent-first communication, execution, coordination and semantic infrastructure for AI systems.

This project is much broader than VERÐANDI and should **not** be copied wholesale.

Useful architectural ideas include:

- capability discovery;
- first-class tool-call messages;
- streaming frames;
- distributed traces;
- binary/compact transport options;
- semantic resource naming;
- distributed agent coordination;
- persistent multi-layer memory;
- distributed state;
- flow control;
- priority queues;
- multi-session orchestration;
- transport bridges;
- self-certifying identity;
- agent-oriented protocol design.

## 3.4.1 Most valuable ideas for VERÐANDI

### A. Capability advertisements

Processes should be able to declare what they can do.

Example:

```json
{
  "event": "capability.advertise",
  "node": "eir",
  "capabilities": [
    "health.inspect",
    "memory.verify",
    "memory.repair"
  ]
}
```

Then planners can ask:

> Who can perform `memory.repair`?

instead of hardcoding a process name.

### B. Capability-based routing

Current event routing broadcasts broadly.

Future optional routing could support:

```text
by event type
by namespace
by capability
by priority
by node
by scope
```

The default should remain broadcast-compatible.

### C. Distributed tracing

Every multi-step operation should get:

```text
trace_id
span_id
parent_span_id
```

This makes it possible to reconstruct:

```text
sensor event
→ salience scoring
→ drive update
→ attention decision
→ planner
→ tool
→ action result
→ memory write
```

This feature would dramatically improve debugging.

### D. Backpressure

If an agent is slow or dead, events should not create unbounded queues.

Optional subscriber policies:

```text
DROP_OLD
DROP_NEW
BUFFER_N
BLOCK
SAMPLE
SUMMARIZE
```

The nerve hub should remain fast even when one subscriber is not.

### E. Distributed node identity

For v0.4+ multi-node VERÐANDI:

```text
node_id
instance_id
agent_id
boot_id
```

should be first-class event metadata.

This solves ambiguity when the same agent moves between machines.

### F. Layered memory

SPINE publicly describes differentiated memory categories.

VERÐANDI should independently formalize:

```text
working memory
episodic memory
semantic memory
procedural memory
identity memory
system memory
```

The nerve transports references and change events.

It should not become the memory database itself.

---

# 4. Feature Comparison Matrix

| Capability | VERÐANDI now | Pulse | Kit Daemon | Connector OS | SPINE | VERÐANDI direction |
|---|---:|---:|---:|---:|---:|---|
| Local event bus | ✅ strong | ✅ | partial | conceptual | ✅ distributed | Preserve |
| Append-only event history | ✅ | ✅ | ✅ | varies | ✅ | Preserve |
| Heartbeat | ✅ | ✅ | ✅ | control loops | varies | Expand to multi-rate loops |
| System self-health | ✅ strong | ✅ | ✅ | ✅ | ✅ | Preserve |
| Circuit breakers | ✅ | partial | partial | conceptual equivalent | partial | Generalize |
| Predictive health | ✅ | partial | partial | control-oriented | partial | Expand |
| Drives | ❌ | ✅ strong | partial | ❌ | partial | Add |
| Salience | limited | ✅ strong | partial | signal weighting | partial | Add |
| Attention scheduling | ❌ | ✅ | partial | routing | routing | Add |
| Emotional persistent state | basic health-derived | ✅ | limited | human-state model | ❌ | Expand cautiously |
| Deterministic reflex skills | actions | ✅ | ✅ | actuators | tools | Generalize |
| Human-state sensing | ❌ | limited | limited | ✅ strong | ❌ | Optional |
| Multi-rate concurrent loops | limited | ✅ | ✅ strong | ✅ | ✅ | Add |
| Capability discovery | ❌ | limited | limited | layers | ✅ strong | Add |
| Trace propagation | limited | limited | limited | limited | ✅ strong | Add |
| Backpressure | limited | unknown | unknown | constraint-based | ✅ | Add |
| Distributed multi-node | planned | ✅ | planned | possible | ✅ strong | Add |
| Identity bundle | ❌ | ✅ | partial | ❌ | identity primitives | Add |
| Adaptive learned weights | ❌ | ✅ | trace learning | adaptive control | neural systems | Add guarded |
| Job queue | reactor/actions | autonomous worker | ✅ | action layer | ✅ | Add separately |
| Memory taxonomy | Mímir/general | ✅ | ✅ | context state | ✅ strong | Formalize |
| Resource governor | health-driven | limited | ✅ | ✅ | infrastructure | Add |
| Security authority model | dry-run/cooldowns | partial | partial | ✅ strong | ✅ | Add |
| Pi-first minimalism | ✅ excellent | moderate | moderate | conceptual | poor fit full-stack | Preserve |

---

# 5. Architectural Principle: VERÐANDI Should Become a Nervous-System Kernel

The key danger is scope creep.

VERÐANDI should **not** become:

- an LLM runtime;
- a browser engine;
- a vector database;
- a monolithic agent framework;
- a full distributed operating system;
- a model trainer;
- a general web protocol.

Instead, make VERÐANDI the:

> **Nervous-system kernel that allows those components to behave like one organism.**

The architectural boundary should be:

```text
VERÐANDI owns:
- events
- routing
- system state
- temporal pulses
- health
- reflexes
- priority metadata
- capability metadata
- local coordination
- node coordination protocol
- observability primitives

VERÐANDI does not own:
- language-model inference
- long-term knowledge retrieval
- full planning
- application UI
- model fine-tuning
- arbitrary web browsing
```

---

# 6. Proposed VERÐANDI vNext Architecture

```text
┌───────────────────────────────────────────────────────────────┐
│                    YGGDRASIL CONTROL PLANE                    │
│ node registry · identity · capabilities · distributed state  │
└──────────────────────────────┬────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│                         ÓÐR LAYER                             │
│ drives · salience · attention · inhibition · resource budget │
└──────────────────────────────┬────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│                      SKULD WORK QUEUE                         │
│ queued work · claims · deadlines · dependencies · outcomes   │
└──────────────────────────────┬────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│                   HJARTSLÁTTUR AUTONOMICS                     │
│ multi-rate loops · health · prediction · homeostasis         │
│ healing · recovery windows · authority gates                 │
└──────────────────────────────┬────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│                      VERÐANDI NERVE                           │
│ pub/sub · event schema · sequencing · trace IDs · priorities │
│ UDS · feed · backpressure · subscriber lifecycle             │
└───────┬──────────────────────┬───────────────────────┬────────┘
        │                      │                       │
        ▼                      ▼                       ▼
    SENSORS                  MEMORY                ACTUATORS
```

The exact Norse names are optional.

The architectural separation is not.

---

# 7. Event Protocol v2

Backward compatibility should be a requirement.

Existing v1 events remain valid.

v2 adds optional metadata.

## 7.1 Proposed event envelope

```json
{
  "_schema": "verdandi.event/2",
  "_seq": 812991,
  "_ts": 1789690073.23,
  "_iso": "2026-09-17T20:47:53-04:00",

  "event": "memory.integrity.warning",
  "source": "mimir",
  "data": {},

  "priority": 60,
  "salience": 0.82,

  "agent_id": "runa",
  "node_id": "pi5-home",
  "instance_id": "heartbeat-01",
  "boot_id": "uuid",

  "trace_id": "uuid",
  "span_id": "uuid",
  "parent_span_id": "uuid",

  "capability": "memory.verify",

  "authority": 1,

  "ttl_seconds": 3600,
  "tags": ["memory", "integrity"]
}
```

Only the original core fields need remain mandatory.

Everything else can be optional.

## 7.2 Priority classes

Suggested internal numeric range:

```text
0–19     background
20–39    low
40–59    normal
60–79    elevated
80–94    urgent
95–100   emergency
```

Do not confuse priority with salience.

A dramatic event can be salient but not actionable.

A boring backup deadline can be low-salience but high-priority.

---

# 8. Multi-Rate Physiology

Replace the assumption of one universal heartbeat with a hierarchy of rhythms.

## 8.1 Reflex loop

Typical interval:

```text
1–5 seconds
```

Purpose:

- service liveness;
- queue emergencies;
- thermal emergencies;
- lockups;
- critical disk conditions.

Must never invoke expensive cognition unless escalation is necessary.

## 8.2 Autonomic loop

Typical interval:

```text
30–90 seconds
```

Purpose:

- health;
- resource utilization;
- breaker status;
- current workload;
- network status.

## 8.3 Awareness loop

Typical interval:

```text
5–15 minutes
```

Purpose:

- goals;
- unfinished tasks;
- curiosity;
- opportunities;
- social state;
- project state.

## 8.4 Consolidation loop

Typical interval:

```text
hours
```

Purpose:

- summarize event clusters;
- merge duplicate memories;
- update statistics;
- compact indexes;
- evaluate learned weights.

## 8.5 Circadian / daily loop

Purpose:

- daily review;
- identity/state snapshot;
- backup;
- memory consolidation;
- activity summary;
- next-day goal preparation.

---

# 9. Drives System

Create a model-independent `DriveRegistry`.

## 9.1 Recommended first drives

```text
goal
curiosity
maintenance
learning
social
unfinished_work
novelty
memory
system_health
user_priority
```

## 9.2 Drive equation

A deliberately simple first version:

```text
new_drive =
    clamp(
        old_drive
        + event_pressure
        + time_pressure
        + goal_pressure
        - decay
        - inhibition,
        0,
        max
    )
```

Do not start with neural reinforcement learning.

Make behavior inspectable first.

## 9.3 Drive events

```text
drive.updated
drive.threshold_crossed
drive.suppressed
drive.satisfied
drive.decayed
```

Every autonomous wake-up should be explainable.

---

# 10. Salience Engine

Implement as a subscriber, not inside the nerve hub.

Inputs may include:

```text
event severity
novelty
recency
goal relevance
human relevance
risk
prediction error
repetition
source reliability
```

Output:

```text
0.0–1.0
```

Initial implementation should be deterministic.

Possible later model-assisted scoring should be optional.

---

# 11. Attention Scheduler

The attention scheduler decides what deserves limited cognitive processing.

Suggested score:

```text
attention_score =
    salience
  × urgency
  × goal_relevance
  × drive_pressure
  × confidence
  × resource_availability
  × permission_factor
```

Then subtract:

```text
cooldown penalty
duplicate penalty
recently handled penalty
cost penalty
risk penalty
```

## 11.1 Important invariant

The attention scheduler may decide **what to think about**.

It must not automatically imply permission to **act**.

Thinking and authority remain separate.

---

# 12. Reflex / Instinct Framework

VERÐANDI already has actions.

Generalize them into reusable reflex packages.

Each reflex declares:

```yaml
name:
version:
triggers:
required_capabilities:
authority_level:
cooldown:
timeout:
resources:
reversible:
```

Possible categories:

```text
healing
maintenance
observation
notification
memory
project
network
resource
```

A reflex should ideally be:

- deterministic;
- fast;
- testable;
- reversible;
- low-cost.

---

# 13. Capability Registry

Add a local capability registry before distributed networking.

## 13.1 Capability record

```text
capability name
provider
version
authority level
input schema
output schema
health
cost estimate
local/remote
last heartbeat
```

Examples:

```text
memory.search
memory.verify
memory.repair
repo.inspect
repo.commit
model.generate
model.embed
calendar.read
network.fetch
```

## 13.2 Discovery

Subscribers publish:

```text
capability.advertise
capability.withdraw
capability.health
```

A registry subscriber maintains the current map.

---

# 14. Resource Governor

A future autonomous system needs a metabolism.

Inputs:

```text
CPU
RAM
VRAM
temperature
battery
power source
network quality
network quota
storage
model load state
human foreground activity
```

The governor produces a budget.

Example:

```text
GREEN
normal operation

YELLOW
avoid large models
defer background work

ORANGE
deterministic reflexes only
pause curiosity/research

RED
survival mode
health + persistence only
```

This is one of the most important Pi-first improvements.

---

# 15. Homeostasis Framework

Create a reusable control primitive:

```text
StateVariable
TargetBand
WarningBand
CriticalBand
Hysteresis
RecoveryWindow
Controller
Actuator
```

Examples:

```text
thermal regulation
queue depth
event rate
LLM wakeups/hour
network consumption
disk growth
memory growth
error rate
```

This converts ad-hoc thresholds into a coherent physiology.

---

# 16. Authority & Permission Model

Add explicit authority metadata.

## Level 0 — Sense

Read-only observation.

Examples:

```text
inspect files
read metrics
check repo status
query memory
```

## Level 1 — Advise

May create recommendations or work items.

## Level 2 — Reversible local action

Examples:

```text
restart own user service
rotate cache
rebuild disposable index
```

## Level 3 — Consequential action

Examples:

```text
modify important files
send external messages
perform network-visible changes
```

Requires explicit policy approval or human permission.

## Level 4 — Restricted

Never autonomously permitted by normal drive pressure.

This ensures:

> Motivation cannot manufacture authority.

---

# 17. Work Queue

Do not abuse the nerve feed as a durable job scheduler.

Create a separate Skuld queue.

## Job schema

```text
job_id
created_at
source_event
goal
priority
deadline
status
claimed_by
required_capabilities
authority
dependencies
attempt_count
max_attempts
result
trace_id
```

## Queue principles

- SQLite first.
- Durable.
- Atomic claims.
- Retry with backoff.
- Dead-letter queue.
- Human-readable.
- No external broker required.

---

# 18. Distributed VERÐANDI

This is the natural v0.4+ evolution.

Do **not** immediately replace UDS.

Use:

```text
local UDS = nerves inside one body/node
secure bridge = long nerve between nodes
```

Each node keeps its own local nerve.

A bridge forwards selected event classes.

## 18.1 Node metadata

```text
node_id
device class
hostname alias
agent identities
capabilities
resource profile
health
last seen
```

## 18.2 Selective federation

Never send every local impulse across the network.

Forward only:

```text
important state changes
capability changes
work assignments
distributed trace metadata
summaries
explicitly shared memory events
```

## 18.3 Conflict resolution

For distributed state:

- immutable event history where practical;
- timestamps + node IDs;
- explicit version numbers;
- later CRDTs only when actually needed.

Do not start with distributed-consensus complexity.

---

# 19. Multi-Agent Coordination

Treat multi-agent systems as multiple nervous-system participants.

Do not create “swarm magic.”

Use explicit mechanics:

```text
identity
capability
job claim
lease
heartbeat
result
confidence
trace
```

Suggested workflow:

```text
task.created
→ capability lookup
→ candidate providers
→ lease granted
→ worker heartbeat
→ result produced
→ verifier checks
→ accepted/rejected
→ memory/event recorded
```

---

# 20. Memory Architecture

Formalize Mímir beyond “one memory system.”

## 20.1 Working memory

Short-lived current context.

## 20.2 Episodic memory

Events that happened.

## 20.3 Semantic memory

Facts and learned abstractions.

## 20.4 Procedural memory

How to perform tasks.

## 20.5 Identity memory

Stable self-description, preferences, long-term commitments.

## 20.6 System memory

Machine state, configuration history, diagnostics.

The nerve should carry:

```text
memory.created
memory.updated
memory.recalled
memory.invalidated
memory.compacted
```

but not necessarily the memory payload itself.

Large payloads should use references.

---

# 21. Identity / Hamr Bundle

Create a portable signed identity package.

Possible independent name:

> **Hamr Bundle**

Contents:

```text
manifest.json
identity.json
preferences.json
drives.json
learned_weights.json
goals.json
capabilities.json
memory_manifest.json
schema_versions.json
checksums.json
signature
```

Explicit exclusions:

```text
API keys
passwords
private tokens
raw private conversation logs by default
```

Uses:

- migrate Runa;
- clone a test agent;
- cold backup;
- restore after device loss;
- compare personality/state evolution.

---

# 22. Learning Without Uncontrolled Self-Modification

Use a staged adaptation pipeline.

```text
OBSERVE
↓
MEASURE
↓
PROPOSE
↓
SIMULATE
↓
TEST
↓
EVALUATE
↓
PROMOTE
```

## 22.1 Safe first learning targets

Allow adaptive changes to:

- drive weights;
- sensor weights;
- cooldown durations within bounds;
- attention priorities;
- model-routing preferences;
- preferred tools;
- scheduling intervals.

Do **not** initially allow autonomous rewriting of:

- security policy;
- authority rules;
- persistence layer;
- updater;
- identity rules;
- core nerve implementation.

---

# 23. Feedback Learning

Store an outcome after significant actions.

```text
expected outcome
actual outcome
cost
latency
success/failure
human feedback
side effects
confidence
```

A simple exponential moving average can adjust weights.

No reinforcement-learning framework is necessary initially.

This produces explainable adaptation.

---

# 24. Observability v2

VERÐANDI should become extremely observable.

Add:

```text
trace IDs
span IDs
loop metrics
drive state
attention decisions
capability health
work queue depth
event rates
subscriber lag
dropped-event counts
resource budgets
authority decisions
```

Recommended command:

```text
verdandi explain <trace-id>
```

Output conceptually:

```text
14:03:02 sensor found repo dirty
14:03:02 salience = 0.44
14:03:02 unfinished_work drive +0.12
14:03:03 attention below threshold
14:18:05 deadline proximity increased urgency
14:18:05 attention threshold crossed
14:18:06 job created
14:18:07 capability provider selected
14:18:08 action denied: authority level insufficient
```

This would be extraordinarily useful for debugging autonomous behavior.

---

# 25. Backpressure and Subscriber Quality

A nervous system should know when one nerve endpoint is overwhelmed.

Per-subscriber metrics:

```text
events received
events processed
lag
queue depth
disconnect count
last ack
last heartbeat
```

Optional policies:

```text
buffer latest N
drop low-priority first
sample repetitive telemetry
disconnect unhealthy consumer
summarize bursts
```

Emergency events should never be silently discarded.

---

# 26. Event Deduplication

Autonomous sensor systems often produce repeated noise.

Add optional fingerprinting:

```text
fingerprint =
    hash(event_type + normalized_source + relevant_data)
```

Policies:

```text
no dedupe
collapse within 5 sec
collapse within 1 min
increment repetition counter
emit summary
```

This will reduce needless LLM wakeups dramatically.

---

# 27. Novelty Detection

Curiosity should be fed by novelty, not random browsing.

Simple v1:

```text
new source?
new event type?
unexpected state transition?
rare value?
first occurrence in N days?
prediction error?
```

Novelty can influence salience and curiosity drive.

---

# 28. Prediction Error

VERÐANDI already predicts system-health trends.

Generalize prediction.

A subsystem can publish:

```text
prediction.created
prediction.resolved
prediction.error
```

Prediction error becomes a learning signal.

This is a useful route toward adaptive behavior without requiring opaque end-to-end reinforcement learning.

---

# 29. Model Router Integration

VERÐANDI should not become an inference engine, but it should understand inference capabilities.

Providers advertise:

```text
model.generate.fast
model.generate.reasoning
model.embed
model.vision
model.code
model.local
model.remote
```

The planner requests a capability rather than a specific vendor/model.

Routing may consider:

```text
quality
latency
privacy
cost
context window
GPU availability
power state
network state
task type
```

This also fits Project A.E.S.I.R.

---

# 30. Sensor SDK

Create a minimal plugin contract.

Conceptually:

```text
setup()
sense()
health()
shutdown()
```

Each sensor returns normalized events.

Suggested first external sensors:

```text
filesystem
git
process
network
calendar
RSS
weather
email metadata
battery
GPU
USB/device presence
local network peers
```

Sensors should never be allowed to mutate state unless they also implement an actuator with a declared authority level.

---

# 31. Actuator SDK

Separate:

```text
I can sense X
```

from:

```text
I can change X.
```

Each actuator declares:

```text
capabilities
authority
reversibility
timeout
rate limits
dry-run support
rollback support
```

---

# 32. Human-State Loop

Borrow the *problem*, not the implementation.

Optional signals may include:

```text
active conversation
quiet hours
typing frequency
calendar busy state
explicit user status
device foreground state
```

Avoid inferring sensitive psychological or medical state unless explicitly configured.

The purpose is simple:

> Don’t wake the agent noisily when the human is busy.

---

# 33. Circadian State

Introduce time-of-day operating modes.

Example:

```text
ACTIVE
QUIET
DEEP_WORK
MAINTENANCE
SLEEP
```

These are system scheduling modes, not claims of biological sleep.

They can adjust:

```text
notification behavior
curiosity
maintenance
memory consolidation
model use
sensor frequency
```

---

# 34. Security Architecture Upgrade

Before network federation, complete a security hardening phase.

## Required additions

- authenticated bridge protocol;
- per-node keys;
- message integrity;
- replay protection;
- capability allowlists;
- authority checks;
- action audit trail;
- rate limiting;
- payload size limits;
- schema validation;
- path traversal protection;
- secret redaction;
- safe serialization;
- bridge deny-by-default;
- node revocation.

## Strong invariant

A remote node should **never** gain more authority than the local policy grants it.

---

# 35. Recommended Things NOT to Import

Some attractive ideas would damage VERÐANDI if added prematurely.

## 35.1 Do not replace UDS with a giant network stack

Local UDS is one of VERÐANDI’s strongest decisions.

## 35.2 Do not require Kubernetes

It would destroy the Pi-first character.

## 35.3 Do not require Redis/Kafka

Optional adapters later are fine.

Core dependency: no.

## 35.4 Do not put neural models in the event hub

Routing must stay deterministic.

## 35.5 Do not make every subsystem “intelligent”

Most nervous-system behavior should be cheap, deterministic machinery.

## 35.6 Do not treat emotional variables as factual consciousness proofs

They are useful internal regulatory state regardless of philosophical interpretation.

## 35.7 Do not adopt uncontrolled autonomous code rewriting

Use bounded adaptation and staged promotion.

## 35.8 Do not make federation mandatory

One Pi must remain a complete valid VERÐANDI body.

---

# 36. Proposed Version Roadmap

---

# v0.4 — **Valhöll**
## Distributed Body Foundation

Goal:

> Let multiple machines become one coordinated body without sacrificing local independence.

Implement:

- node identity;
- instance identity;
- boot identity;
- secure bridge prototype;
- distributed heartbeat summaries;
- capability advertisements;
- capability registry;
- trace IDs and span IDs;
- remote-event allowlist;
- node health registry;
- federation metrics.

Exit criteria:

- two nodes can discover one another;
- selected events cross the bridge;
- local operation continues when disconnected;
- node disappearance is detected;
- no remote action occurs without explicit permission;
- complete trace across both nodes.

---

# v0.5 — **Óðr**
## Drives, Salience and Attention

Goal:

> Give the nervous system endogenous priority without putting cognition in the nerve.

Implement:

- drive registry;
- deterministic drive update engine;
- drive decay;
- drive thresholds;
- salience field;
- salience processor;
- attention scheduler;
- inhibition/cooldown;
- novelty scoring;
- explainable attention decisions.

Initial drives:

- system_health;
- unfinished_work;
- goal;
- curiosity;
- learning;
- memory;
- user_priority.

Exit criteria:

- system autonomously chooses among competing stimuli;
- every choice has an explanation trace;
- drive values survive restart;
- no LLM is necessary for basic prioritization.

---

# v0.6 — **Heimdallr**
## Regulation, Authority and Homeostasis

Goal:

> Build a proper autonomic control layer.

Implement:

- reusable hysteresis primitive;
- target bands;
- recovery windows;
- resource governor;
- hard/soft constraints;
- authority levels;
- actuator permissions;
- rate limits;
- action budgets;
- safe-mode state;
- thermal/power/network metabolic states.

Exit criteria:

- resource scarcity automatically degrades optional cognition;
- unsafe actions are blocked independent of model output;
- recovery does not oscillate;
- all actuator execution is auditable.

---

# v0.7 — **Skuldarverk**
## Durable Work and Reflex System

Goal:

> Separate impulses from work.

Implement:

- SQLite work queue;
- job claims;
- leases;
- retries;
- deadlines;
- dependencies;
- dead-letter queue;
- reflex/instinct packages;
- deterministic-first execution;
- model escalation only when needed.

Exit criteria:

- jobs survive process restart;
- two workers cannot claim the same lease accidentally;
- failed work retries safely;
- reflexes work without LLM inference.

---

# v0.8 — **Mímisbrunnr**
## Memory Physiology

Goal:

> Turn memory into a structured organ system.

Implement:

- memory taxonomy;
- memory event protocol;
- content-addressed references;
- working-memory expiry;
- episodic summaries;
- semantic updates;
- procedural memory;
- identity memory;
- memory health metrics;
- consolidation scheduler;
- memory invalidation.

Exit criteria:

- nerve carries references rather than giant payloads;
- memories can be traced back to events;
- stale/invalid memory can be revoked;
- consolidation works offline.

---

# v0.9 — **Hamr**
## Identity and Adaptive Continuity

Goal:

> Make an agent portable without making it stateless.

Implement:

- signed identity bundle;
- schema versioning;
- goal export/import;
- drive export/import;
- capability manifest;
- learned weight export/import;
- memory manifest;
- secret exclusion;
- integrity verification;
- safe adaptive weight learning.

Exit criteria:

- migrate an agent between two machines;
- verify identity bundle integrity;
- preserve behavioral state;
- restore from backup;
- secrets remain outside bundle.

---

# v0.10 — **Huginn**
## Cognitive Orchestration

Goal:

> Connect nervous-system state to reasoning intelligently.

Implement:

- model capability registry;
- task-to-model routing;
- cognition budget;
- context assembler;
- attention-triggered reasoning;
- specialist worker delegation;
- verifier/reviewer role;
- result confidence;
- prediction/resolution events.

Exit criteria:

- simple tasks never wake expensive models unnecessarily;
- high-complexity jobs can route to specialist models;
- reasoning actions remain traceable to nerve events;
- model failure falls back cleanly.

---

# v0.11 — **Muninn**
## Learning and Consolidation

Goal:

> Let successful experience change future behavior safely.

Implement:

- outcome tracking;
- prediction-error events;
- bounded adaptive weights;
- sensor reliability scores;
- tool reliability scores;
- model-routing learning;
- scheduled evaluation;
- rollback of bad learned parameters;
- replay-based offline evaluation.

Exit criteria:

- measurable improvement on benchmark tasks;
- all learned state inspectable;
- all learned state reversible;
- no modification to authority/security policy.

---

# v0.12 — **Yggdrasil**
## Distributed Nervous-System Release Candidate

Goal:

> A coherent local-first digital organism architecture across heterogeneous hardware.

Implement/harden:

- multi-node discovery;
- secure federation;
- capability routing;
- distributed job scheduling;
- memory reference federation;
- failover;
- resource-aware placement;
- observability dashboard;
- benchmark suite;
- chaos/failure testing;
- formal compatibility spec.

Exit criteria:

- Pi + laptop + server function as one system;
- any node can disappear without corrupting the whole;
- critical history survives;
- local nodes retain autonomy;
- federation remains optional.

---

# v1.0 — **Yggdrasil Stable**
## Nervous-System Kernel for Persistent AI Agents

Requirements:

- protocol stability;
- migration tooling;
- compatibility tests;
- security review;
- long-running soak tests;
- clear extension SDK;
- documented threat model;
- Pi validation;
- desktop validation;
- multi-node validation;
- deterministic fallback mode;
- extensive observability;
- clean failure behavior.

---

# 37. Recommended Implementation Order

Do not implement the roadmap strictly by “coolness.”

Best engineering order:

```text
1. Trace IDs
2. Node/instance identity
3. Capability registry
4. Multi-rate loop scheduler
5. Generic hysteresis
6. Resource governor
7. Authority model
8. Drive registry
9. Salience
10. Attention scheduler
11. Durable work queue
12. Reflex packages
13. Backpressure
14. Distributed bridge
15. Memory taxonomy
16. Identity bundle
17. Adaptive weights
18. Cognitive router
19. Multi-agent scheduling
20. Distributed memory
```

This order gives later systems trustworthy foundations.

---

# 38. First Development Sprint

A realistic first sprint should **not** attempt “autonomous consciousness.”

It should add infrastructure that everything else can use.

## Sprint A — Event Protocol v2

Add optional:

```text
schema
source
priority
salience
agent_id
node_id
instance_id
boot_id
trace_id
span_id
parent_span_id
authority
ttl
tags
```

Requirements:

- v1 compatibility;
- no mandatory new fields;
- round-trip tests;
- malformed metadata ignored or rejected predictably;
- no measurable regression in ordinary local publish latency.

## Sprint B — Trace engine

Add helper library:

```text
new_trace()
child_span()
current_trace()
trace_context()
```

Instrument:

- heartbeat;
- reactor;
- actions;
- checks;
- context injector;
- conversation logger.

## Sprint C — Capability registry

Implement:

```text
advertise
withdraw
lookup
health
expire
```

SQLite or in-memory + persisted snapshot.

## Sprint D — Multi-rate scheduler

Implement generic periodic tasks with:

```text
interval
jitter
priority
budget
timeout
enabled
failure policy
```

Migrate existing heartbeat behavior onto it only after tests prove parity.

---

# 39. Second Development Sprint

## Drives v1

Implement deterministic drives only.

No model calls.

Inputs:

- events;
- timers;
- goals;
- health;
- queue state.

Outputs:

```text
drive.updated
drive.threshold_crossed
```

## Salience v1

Rule-based.

## Attention v1

Priority queue with transparent scoring.

## Explanation CLI

Commands:

```text
verdandi drives
verdandi attention
verdandi explain <trace>
verdandi capabilities
```

---

# 40. Third Development Sprint

## Resource governor

Add:

- CPU;
- RAM;
- disk;
- temperature;
- battery if available;
- GPU/VRAM if available;
- network state.

## Authority framework

All actions declare authority.

## Safe mode

When resources or integrity degrade:

```text
pause curiosity
pause background research
pause expensive models
preserve heartbeat
preserve memory writes
preserve essential recovery
```

---

# 41. Testing Strategy

Every new physiological metaphor needs a boring engineering test.

## Unit tests

- drive accumulation;
- decay;
- threshold crossing;
- hysteresis;
- salience scoring;
- attention ordering;
- capability expiry;
- lease expiration;
- authority rejection;
- resource budgets.

## Integration tests

- sensor → event → drive → attention → job;
- job → capability → worker → result;
- failure → breaker → recovery;
- network loss → local continuation;
- node reconnect → state reconciliation.

## Property tests

Useful invariants:

```text
sequence numbers never decrease
drive never leaves configured bounds
unauthorized action never executes
one job lease has one active owner
critical event is never silently dropped
v1 event remains readable by v2
recovery requires required stability interval
```

## Chaos tests

Kill:

- hub;
- heartbeat;
- SQLite connection;
- bridge;
- worker;
- model service;
- network;
- disk-write path.

Then confirm graceful behavior.

---

# 42. Benchmark Suite

Create **VerdandiBench**.

Metrics:

```text
event publish latency
broadcast latency
events/sec
CPU idle overhead
RAM idle overhead
heartbeat jitter
subscriber lag
drop rate
recovery time
bridge latency
job claim latency
trace overhead
drive update latency
Pi temperature impact
```

Primary target platforms:

```text
Raspberry Pi 5 16GB
ordinary Linux laptop
GPU laptop
server laptop
```

A feature that doubles idle power for tiny benefit should be questioned.

---

# 43. Compatibility Rules

## Rule 1

A minimal installation needs only:

```text
Python
stdlib
SQLite
local filesystem
```

unless a feature explicitly declares an optional dependency.

## Rule 2

Network federation is optional.

## Rule 3

LLM integration is optional.

## Rule 4

One-node operation is first-class.

## Rule 5

Old v1 publishers continue functioning.

## Rule 6

Extensions communicate through documented interfaces rather than importing each other’s internals.

---

# 44. Plugin Boundaries

Recommended package boundaries:

```text
verdandi-core
verdandi-heartbeat
verdandi-regulation
verdandi-drives
verdandi-attention
verdandi-capabilities
verdandi-work
verdandi-memory
verdandi-identity
verdandi-bridge
verdandi-cognition
verdandi-observability
```

This can remain one repository initially.

The boundaries matter more than packaging.

---

# 45. What Makes VERÐANDI Distinct

After these additions, VERÐANDI should still not market itself as “another agent framework.”

Its distinctive proposition would be:

> **A lightweight, local-first nervous-system substrate that gives independent AI processes a shared present, autonomic health, endogenous priorities, durable work, capability awareness, and optional distributed continuity.**

That is a meaningful category.

Its strongest differentiators remain:

- tiny local core;
- Unix-domain-socket nerve;
- append-only continuity;
- model independence;
- hardware ownership;
- Raspberry Pi viability;
- graceful degradation;
- explicit self-healing;
- mythology that maps cleanly to architecture;
- optional rather than mandatory distribution.

---

# 46. Clean-Room Feature Adoption Ledger

Use this table whenever an outside architecture inspires work.

| ID | Observed concept | Public source | Abstract requirement | VERÐANDI-native design | External code read? | Independent tests? |
|---|---|---|---|---|---|---|
| CR-001 | Drive pressure | Pulse docs | persistent endogenous priority | DriveRegistry | No | Required |
| CR-002 | Autonomous skill trigger | Pulse docs | deterministic fast response | Reflex packages | No | Required |
| CR-003 | Concurrent background loops | Kit docs | multiple timescale physiology | MultiRateScheduler | No | Required |
| CR-004 | Homeostatic control | Connector OS docs | stable bounded regulation | ControlBand primitive | No | Required |
| CR-005 | Capability discovery | SPINE docs | locate available function | CapabilityRegistry | No | Required |
| CR-006 | Distributed tracing | SPINE docs | explain multi-step behavior | TraceContext | No | Required |
| CR-007 | Portable identity | Pulse docs | migrate persistent state | Hamr Bundle | No | Required |
| CR-008 | Adaptive weighting | Pulse/Kit docs | improve priorities from outcomes | bounded EMA learner | No | Required |

Keep this ledger in the repository.

It creates a paper trail demonstrating independent design.

---

# 47. Research Notes on Licensing

At the research snapshot:

- Pulse publicly presents an MIT-licensed core.
- Kit Daemon publicly presents itself as MIT licensed.
- Connector OS publicly presents itself as MIT licensed.
- SPINE publicly presents AGPL-3.0-or-later plus a commercial licensing option.
- VERÐANDI is MIT licensed.

Even where a permissive license would permit code reuse, the roadmap deliberately recommends **architecture-level clean-room reimplementation**.

For SPINE especially, keeping the research at the conceptual/interface level prevents accidental entanglement with AGPL implementation details.

Always verify current licenses before intentionally incorporating any external code.

---

# 48. Source Registry

Research snapshot taken 2026-09-17.

## VERÐANDI

Repository:

https://github.com/hrabanazviking/Verdandi

Relevant public docs:

```text
README.md
docs/architecture.md
docs/roadmap.md
docs/agi-architecture-patterns.md
docs/security.md
docs/monitoring.md
```

## Pulse

Repository:

https://github.com/Hypostas/pulse

Architecture synopsis:

https://github.com/Hypostas/pulse/blob/main/NERVOUS-SYSTEM.md

Observed concepts used in this research:

```text
persistent drives
salience
attention
identity bundle
autonomous skills
feedback learning
multi-agent coordination
```

## Kit Daemon

Repository:

https://github.com/Kadatha/Kit-Daemon

Observed concepts used in this research:

```text
multiple asynchronous loops
self-diagnosis
auto-repair
autonomous worker
local inference
skill evolution
trace-driven improvement
```

## Connector OS

Repository:

https://github.com/leenathomas01/connector-os

Observed concepts used in this research:

```text
control theory
threshold regulation
hysteresis
sensing
actuation
human-state loop
external constraints
recovery
authority regulation
```

## SPINE

Repository:

https://github.com/nervosys/SPINE

Observed concepts used in this research:

```text
agent-native protocol concepts
capability discovery
distributed tracing
flow control
multi-agent coordination
distributed memory
semantic identity/naming
```

---

# 49. Final Architectural Recommendation

VERÐANDI should evolve by **growing outward from the nerve**, not by bloating the nerve itself.

The progression should be:

```text
NERVE
   ↓
HEARTBEAT
   ↓
HOMEOSTASIS
   ↓
DRIVES
   ↓
ATTENTION
   ↓
WORK
   ↓
MEMORY
   ↓
IDENTITY
   ↓
COGNITION
   ↓
DISTRIBUTED BODY
```

That order matters.

A reasoning model without those layers is a brain waiting for prompts.

A nervous system without reasoning is an organism with reflexes but little deliberation.

The interesting architecture emerges when both remain separate enough to be understandable, but connected tightly enough to behave as one system.

VERÐANDI already possesses the hardest foundational insight:

> **Continuity is not created merely by giving an LLM more context. Continuity comes from connecting processes, state, memory, time, sensing, reaction, and persistence into one ongoing system.**

The next generations should deepen that insight rather than abandon it.

---

# 50. One-Sentence North Star

> **VERÐANDI should become the lightweight, local-first digital nervous-system kernel that lets models, memories, sensors, tools, devices, and agents experience one shared, persistent present.**

