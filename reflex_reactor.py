#!/usr/bin/env python3
"""Verdandi first reflex set through the reactor (VD-T3).

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
"""
import time
from dataclasses import dataclass, field

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
    def __init__(self, binding, handlers=None, starter=None):
        self.binding = binding
        self.registry = binding.registry
        self.awareness = []
        self.watch_levels = {}
        self.shed_sources = {}
        self.started = []
        self.spoken = []
        self.firings = []
        self.latencies = {}
        self._starter = starter or (lambda name: self.started.append(name) or {"started": name})
        self.handlers = {"notify": self._do_notify, "brace": self._do_brace, "shed": self._do_shed, "wake": self._do_wake, "speak": self._do_speak}
        if handlers:
            self.handlers.update(handlers)
        for decl in [self.registry.get(n) for n in self.registry.names()]:
            if decl.action not in ACTIONS:
                raise UnknownActionError(f"reflex {decl.name!r}: unknown action {decl.action!r}")
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
        for verdict in self.binding.judge_event(event):
            if not verdict.fire:
                continue
            decl = self.registry.require(verdict.reflex)
            t0 = time.perf_counter_ns()
            effect = self.handlers[decl.action](decl, event)
            latency_ms = (time.perf_counter_ns() - t0) / 1e6
            f = Firing(reflex=decl.name, action=decl.action, event=dict(event), basis=verdict.basis, judge=verdict.judge, latency_ms=latency_ms, effect=effect if isinstance(effect, dict) else {"result": effect})
            self.firings.append(f); self.latencies.setdefault(decl.name, []).append(latency_ms); out.append(f)
        return out
    def process_stream(self, events):
        out = []
        for e in events:
            out.extend(self.process_event(e))
        return out
