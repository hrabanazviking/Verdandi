#!/usr/bin/env python3
"""Verdandi first reflex set through the reactor (VD-T3) + safety rails (VD-T5).

Declared reflexes, judged by HugrGate (VD-T2 binding), fired through a
reactor-side executor. The five first actions:
  notify - surface to awareness (params: channel)
  brace  - raise watch level on a feed
  shed   - drop a noisy source to summary rate (params: summary_rate_seconds)
  wake   - start a named process (params/event: process)
  speak  - emit a stock phrase to a named channel (params: phrase, channel)
Each firing is timed with perf_counter; latency_ms is recorded on the
firing record. A reflex fires only on a judged fire verdict - never
on its trigger alone, never unjudged, never if undeclared.
Handlers are injectable for tests; defaults record effects in-memory
(wake uses an injectable starter, default records only, spawns nothing).

Safety rails (VD-T5), all owner-controlled, checked after judgment and
before the action runs, so a blocked reflex never executes its action:
  - per-reflex rate limit: decl.rate_limit_per_minute, sliding 60s window
  - per-reflex disable: disable_reflex(name) / enable_reflex(name)
  - one global kill switch: set_kill_switch(True/False), effective
    immediately (the very next judged firing is blocked)
  - quiet state: set_quiet(True/False); no reflex fires in quiet
  - error self-disable: a reflex whose action errors twice in a row
    disables itself and reports (safety_reports + logging), rather
    than retrying forever. A success resets the consecutive count.
Blocked firings are recorded in self.blocked with their reason; they
are not firings and are not written to the firing record as firings.
"""
import logging
import time
from dataclasses import dataclass, field

log = logging.getLogger("verdandi.reflex_reactor")

ACTIONS = ("notify", "brace", "shed", "wake", "speak")

class UnknownActionError(ValueError):
    code = "unknown_action"

@dataclass
class Firing:
    reflex: str
    action: str
    event: dict
    basis: str
    judge: str
    latency_ms: float
    effect: dict = field(default_factory=dict)
    def to_dict(self):
        return {"reflex": self.reflex, "action": self.action, "event": self.event, "basis": self.basis, "judge": self.judge, "latency_ms": self.latency_ms, "effect": self.effect}

class ReflexReactor:
    def __init__(self, binding, handlers=None, starter=None, record=None, clock=None, observer=None):
        self.binding = binding
        self.registry = binding.registry
        # Optional metacognitive observation. No action originates from this
        # observer: owner-granted reflexes still execute only after judgment.
        self.observer = observer
        self.observations = []
        self.awareness = []
        self.watch_levels = {}
        self.shed_sources = {}
        self.started = []
        self.spoken = []
        self.record = record
        self.firings = []
        self.latencies = {}
        # VD-T5 safety rails state
        self._clock = clock or time.monotonic
        self._fire_times = {}
        self.disabled = set()
        self.kill_switch = False
        self.quiet = False
        self.blocked = []
        self.safety_reports = []
        self._consecutive_errors = {}
        self._starter = starter or (lambda name: self.started.append(name) or {"started": name})
        self.handlers = {"notify": self._do_notify, "brace": self._do_brace, "shed": self._do_shed, "wake": self._do_wake, "speak": self._do_speak}
        if handlers:
            self.handlers.update(handlers)
        for decl in [self.registry.get(n) for n in self.registry.names()]:
            if decl.action not in ACTIONS:
                raise UnknownActionError(f"reflex {decl.name!r}: unknown action {decl.action!r}")
    # --- owner controls (VD-T5) ---
    def disable_reflex(self, name):
        self.registry.require(name)
        self.disabled.add(name)
    def enable_reflex(self, name):
        self.registry.require(name)
        self.disabled.discard(name)
        self._consecutive_errors.pop(name, None)
    def set_kill_switch(self, on):
        self.kill_switch = bool(on)
    def set_quiet(self, on):
        self.quiet = bool(on)
    def _report(self, kind, reflex, detail):
        entry = {"kind": kind, "reflex": reflex, "detail": detail}
        self.safety_reports.append(entry)
        log.error("Verdandi reflex safety: %s", entry)
        return entry
    def _block_reason(self, decl):
        if self.kill_switch:
            return "kill_switch"
        if self.quiet:
            return "quiet_state"
        if decl.name in self.disabled:
            return "disabled"
        now = self._clock()
        window = [t for t in self._fire_times.get(decl.name, []) if now - t < 60.0]
        self._fire_times[decl.name] = window
        if len(window) >= decl.rate_limit_per_minute:
            return "rate_limit"
        return None
    def _do_notify(self, decl, event):
        e = {"channel": decl.params.get("channel", "awareness"), "event": event, "reflex": decl.name}
        self.awareness.append(e); return e
    def _do_brace(self, decl, event):
        feed = event.get("feed", decl.params.get("feed", "*"))
        level = decl.params.get("watch_level", "high")
        self.watch_levels[feed] = level
        return {"feed": feed, "watch_level": level}
    def _do_shed(self, decl, event):
        src = event.get("source", event.get("feed", "unknown"))
        rate = decl.params.get("summary_rate_seconds", 60)
        self.shed_sources[src] = rate
        return {"source": src, "summary_rate_seconds": rate}
    def _do_wake(self, decl, event):
        name = event.get("process", decl.params.get("process", ""))
        if not name:
            raise ValueError("wake: no process named")
        r = self._starter(name)
        return r if isinstance(r, dict) else {"started": name}
    def _do_speak(self, decl, event):
        e = {"channel": decl.params.get("channel", "default"), "phrase": decl.params.get("phrase", ""), "reflex": decl.name}
        self.spoken.append(e); return e
    def process_event(self, event):
        out = []
        if self.observer is not None:
            try:
                proposals = self.observer.observe(event)
                # Bounded operational view, never a durable event payload log.
                self.observations.extend(proposals)
                del self.observations[:-256]
            except Exception as exc:
                log.warning("Verdandi optional observation failed: %s", type(exc).__name__)
                # Observation cannot bypass reflex judgment or interrupt nerve flow.
        for verdict in self.binding.judge_event(event):
            if not verdict.fire:
                if self.record is not None:
                    self.record.record_no_fire(verdict, event)
                continue
            decl = self.registry.require(verdict.reflex)
            reason = self._block_reason(decl)
            if reason is not None:
                self.blocked.append({"reflex": decl.name, "reason": reason, "event": dict(event)})
                continue
            t0 = time.perf_counter_ns()
            try:
                effect = self.handlers[decl.action](decl, event)
            except Exception as e:
                count = self._consecutive_errors.get(decl.name, 0) + 1
                self._consecutive_errors[decl.name] = count
                self._report("reflex_error", decl.name, f"{type(e).__name__}: {e} (consecutive={count})")
                if count >= 2:
                    self.disabled.add(decl.name)
                    self._report("reflex_self_disabled", decl.name, f"disabled after {count} consecutive errors: {type(e).__name__}: {e}")
                continue
            self._consecutive_errors.pop(decl.name, None)
            latency_ms = (time.perf_counter_ns() - t0) / 1e6
            self._fire_times.setdefault(decl.name, []).append(self._clock())
            f = Firing(reflex=decl.name, action=decl.action, event=dict(event), basis=verdict.basis, judge=verdict.judge, latency_ms=latency_ms, effect=effect if isinstance(effect, dict) else {"result": effect})
            self.firings.append(f); self.latencies.setdefault(decl.name, []).append(latency_ms); out.append(f)
            if self.record is not None:
                self.record.record_firing(f)
        return out
    def process_stream(self, events):
        out = []
        for e in events:
            out.extend(self.process_event(e))
        return out
