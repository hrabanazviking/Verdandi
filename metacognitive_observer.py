"""Verdandi's optional, bounded metacognitive event observer.

Observe what the nervous system is doing, detect changes and repeat patterns,
and propose reversible next steps. This module never executes actions, contacts
a model by default, edits memory, or retains raw event payloads. It is separate
from the fast Unix-domain-socket transport and compatible with read-only
Second Brain clients.

For uncertain cases, an optional HugrGate-style callable accepts only a
redacted observation summary and returns:
    {"escalate": bool, "basis": str, "confidence": float | None}
This is an injected adapter contract, NOT a claim that any particular
HugrGate HTTP endpoint is already deployed. No unjudged automatic reactions.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Callable, Mapping


_ACTIONS = frozenset({
    "inspect", "notify", "review_change", "reduce_load",
    "request_evidence", "defer",
})
_LEVELS = frozenset({"info", "warning", "critical"})
_RESULT_CAP = 256


@dataclass(frozen=True)
class Observation:
    """Ephemeral, content-minimized observation with a proposed next step."""

    category: str
    severity: str
    source: str
    count: int
    reason: str
    suggested_action: str
    digest: str
    judge: str = "deterministic"
    confidence: float | None = None

    def to_dict(self) -> dict:
        return {
            "category": self.category, "severity": self.severity,
            "source": self.source, "count": self.count,
            "reason": self.reason, "suggested_action": self.suggested_action,
            "digest": self.digest, "judge": self.judge,
            "confidence": self.confidence,
        }


class MetacognitiveObserver:
    """Analyze incoming event metadata using bounded, volatile working state.

    Detector budgets and cooldowns prevent reactivity loops or alert floods.
    An observer proposes actions; a separate declared, granted and judged
    ReflexReactor is the ONLY component allowed to execute them.

    `judge` is optional. If present, it sees only category, source, severity,
    count and a digest, never original payloads or temporary conversation text.
    The judge cannot invent an action or override the allowed-action list.
    """

    def __init__(
        self,
        *,
        window_seconds: float = 60.0,
        burst_threshold: int = 8,
        failure_threshold: int = 3,
        slow_latency_ms: float = 3000.0,
        cooldown_seconds: float = 30.0,
        max_events: int = 2048,
        judge: Callable[[Mapping], Mapping] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if window_seconds <= 0 or cooldown_seconds < 0 or max_events < 1:
            raise ValueError("invalid observation budget")
        if burst_threshold < 2 or failure_threshold < 1 or slow_latency_ms <= 0:
            raise ValueError("invalid observer threshold")
        self.window_seconds = float(window_seconds)
        self.burst_threshold = burst_threshold
        self.failure_threshold = failure_threshold
        self.slow_latency_ms = float(slow_latency_ms)
        self.cooldown_seconds = float(cooldown_seconds)
        self.max_events = max_events
        self.judge = judge
        self.clock = clock
        self._events: deque[tuple[float, str, str, str, bool]] = deque(maxlen=max_events)
        self._states: dict[str, str] = {}
        self._last_alert: dict[tuple[str, str], float] = {}
        self._latest: deque[Observation] = deque(maxlen=_RESULT_CAP)
        self.total_seen = 0
        self.judge_calls = 0
        self.judge_failures = 0
        self.suppressed = 0

    @staticmethod
    def _bounded(value: object, max_chars: int = 80) -> str:
        if not isinstance(value, (int, float, str)):
            return "unknown"
        return str(value).strip()[:max_chars] or "unknown"

    @staticmethod
    def _digest(event: Mapping) -> str:
        # Digest is not a source of truth or a substitute for provenance.
        # Ignore transport counters/time, so repeat patterns are detectable.
        relevant = {
            key: event.get(key)
            for key in ("source", "event_type", "type", "kind", "state",
                        "severity", "status", "error_code")
            if key in event
        }
        serial = json.dumps(relevant, sort_keys=True, default=str)
        return hashlib.sha256(serial.encode("utf-8")).hexdigest()[:20]

    def _expire(self, now: float) -> None:
        while self._events and now - self._events[0][0] > self.window_seconds:
            self._events.popleft()
        # Also bound auxiliary state. This is NOT an event archive.
        if len(self._states) > self.max_events:
            self._states.clear()
        if len(self._last_alert) > self.max_events:
            self._last_alert.clear()

    def _propose(
        self, *,
        category: str, severity: str, source: str,
        count: int, reason: str, action: str, digest: str,
        now: float,
    ) -> Observation | None:
        if action not in _ACTIONS or severity not in _LEVELS:
            raise ValueError("invalid observation action/severity")
        key = (source, category)
        last = self._last_alert.get(key)
        if last is not None and now - last < self.cooldown_seconds:
            self.suppressed += 1
            return None
        self._last_alert[key] = now
        judge_name = "deterministic"
        confidence = None
        if self.judge is not None:
            # The judge is a candidate filter, not an action executor or a
            # source of arbitrary code/actions. Fail closed on error.
            self.judge_calls += 1
            summary = {
                "category": category, "severity": severity,
                "source": source, "count": count, "digest": digest,
                "proposed_action": action,
            }
            try:
                verdict = self.judge(summary)
                if not isinstance(verdict, Mapping) or not isinstance(verdict.get("escalate"), bool):
                    raise ValueError("malformed meta-verdict")
                if not verdict["escalate"]:
                    self.suppressed += 1
                    return None
                reason_text = verdict.get("basis")
                if not isinstance(reason_text, str) or not reason_text.strip():
                    raise ValueError("empty meta-verdict basis")
                # Don't trust a judge-supplied string as a command.
                reason += " | judge: " + reason_text[:160]
                raw_conf = verdict.get("confidence")
                if type(raw_conf) in (int, float) and math.isfinite(raw_conf) and 0 <= raw_conf <= 1:
                    confidence = float(raw_conf)
                judge_name = "hugrgate-adapter"
            except Exception:
                self.judge_failures += 1
                self.suppressed += 1
                return None
        item = Observation(
            category=category, severity=severity, source=source,
            count=count, reason=reason, suggested_action=action,
            digest=digest, judge=judge_name, confidence=confidence,
        )
        self._latest.append(item)
        return item

    def observe(self, event: Mapping) -> list[Observation]:
        """Observe only metadata; return proposals without executing or persisting."""
        if not isinstance(event, Mapping):
            raise TypeError("event must be a mapping")
        now = float(self.clock())
        self.total_seen += 1
        self._expire(now)
        source = self._bounded(event.get("source", "unknown"))
        kind = self._bounded(event.get("event_type", event.get("kind", event.get("type", "event"))))
        severity = self._bounded(event.get("severity", event.get("status", "info"))).lower()
        error = severity in {"error", "critical", "failed", "failure"} or bool(event.get("failed") is True)
        digest = self._digest(event)
        self._events.append((now, source, kind, digest, error))
        same_source = [e for e in self._events if e[1] == source]
        failures = sum(e[4] for e in same_source)
        repetitions = sum(e[3] == digest for e in same_source)
        proposals: list[Observation] = []

        def add(category: str, level: str, count: int, reason: str, action: str) -> None:
            result = self._propose(
                category=category, severity=level, source=source, count=count,
                reason=reason, action=action, digest=digest, now=now,
            )
            if result:
                proposals.append(result)

        if len(same_source) >= self.burst_threshold:
            add("event_pressure", "warning", len(same_source),
                "high event rate in bounded window", "reduce_load")
        if failures >= self.failure_threshold:
            add("repeated_failure", "critical", failures,
                "repeated failure signals in bounded window", "inspect")
        if repetitions >= self.burst_threshold:
            add("repeat_loop", "warning", repetitions,
                "same event signature repeated", "inspect")

        state = event.get("state")
        if isinstance(state, str):
            previous = self._states.get(source)
            self._states[source] = self._bounded(state)
            if previous is not None and previous != state:
                add("state_transition", "info", 1,
                    "observed a state transition", "review_change")

        latency = event.get("latency_ms")
        if type(latency) in (int, float) and math.isfinite(latency) and latency >= self.slow_latency_ms:
            add("slow_operation", "warning", 1,
                "operation exceeded configured latency threshold", "inspect")

        if event.get("evidence_conflict") is True or event.get("contradiction") is True:
            add("evidence_conflict", "warning", 1,
                "source-reported evidence conflict requires review", "request_evidence")
        elif event.get("uncertain") is True or event.get("missing_evidence") is True:
            add("uncertain_observation", "info", 1,
                "uncertainty reported without enough source evidence", "defer")

        return proposals

    def snapshot(self) -> dict:
        """Content-minimized operational self-model, not a conscious-state claim."""
        counts = Counter(e[2] for e in self._events)
        return {
            "events_in_window": len(self._events),
            "events_total": self.total_seen,
            "event_kinds": dict(counts.most_common(20)),
            "proposals_in_memory": len(self._latest),
            "judge_calls": self.judge_calls,
            "judge_failures": self.judge_failures,
            "suppressed": self.suppressed,
            "recent_categories": [o.category for o in list(self._latest)[-12:]],
        }

    def clear(self) -> None:
        """Explicitly purge temporary working memory; default is no persistence."""
        self._events.clear()
        self._states.clear()
        self._last_alert.clear()
        self._latest.clear()
