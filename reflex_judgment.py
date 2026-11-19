#!/usr/bin/env python3
"""Verdandi HugrGate judgment binding (VD-T2).

Verdandi sends candidate events to HugrGate's reflex API and receives
fire / no-fire with basis. Until HugrGate's HG-T4 lands on her readiness
branch, this slice is built against a fixture judge implementing the
same verdict schema, and the swap to the live binding is recorded as
owed re-proof (see campaign/READINESS_PROGRESS.md).

Verdict schema (the contract both judges implement):
    {"reflex": <name>, "fire": <bool>, "basis": <non-empty str>,
     "judge": <judge id>}

Safety rule: no reflex fires unjudged. A dead, unreachable or
malformed judge degrades Verdandi to awareness-only: every verdict is
no-fire, the binding is marked degraded, and the degradation is logged
(standard logging, plus an in-memory record), never silent.
"""
import json
import logging
import urllib.request
from dataclasses import dataclass

log = logging.getLogger("verdandi.reflex_judgment")


class JudgeUnavailableError(RuntimeError):
    """The judge cannot be reached or cannot answer."""


class MalformedVerdictError(ValueError):
    """The judge answered, but not in the verdict schema."""


@dataclass(frozen=True)
class Verdict:
    reflex: str
    fire: bool
    basis: str
    judge: str
    degraded: bool = False

    def to_dict(self):
        return {"reflex": self.reflex, "fire": self.fire,
                "basis": self.basis, "judge": self.judge,
                "degraded": self.degraded}


def _validate_verdict(raw, reflex_name):
    if not isinstance(raw, dict):
        raise MalformedVerdictError("verdict is not an object")
    fire = raw.get("fire")
    if not isinstance(fire, bool):
        raise MalformedVerdictError("verdict 'fire' must be a boolean")
    basis = raw.get("basis")
    if not isinstance(basis, str) or not basis.strip():
        raise MalformedVerdictError("verdict 'basis' must be a non-empty string")
    return Verdict(reflex=str(raw.get("reflex", reflex_name)),
                   fire=fire, basis=basis,
                   judge=str(raw.get("judge", "unknown")))


def _trigger_basis(trigger, event):
    """Check each trigger condition against the event.

    Returns (matched, basis_parts). Supported condition forms:
    exact equality, '*', and the suffix operators _gte / _lte / _gt / _lt.
    """
    parts = []
    matched = True
    for key, want in trigger.items():
        op = "eq"
        field = key
        for suffix, name in (("_gte", "gte"), ("_lte", "lte"),
                             ("_gt", "gt"), ("_lt", "lt")):
            if key.endswith(suffix):
                field, op = key[:-len(suffix)], name
                break
        got = event.get(field)
        if op == "eq":
            ok = (want == "*") or (got == want)
        elif got is None:
            ok = False
        else:
            try:
                ok = {"gte": got >= want, "lte": got <= want,
                      "gt": got > want, "lt": got < want}[op]
            except TypeError:
                ok = False
        matched = matched and ok
        parts.append(f"{key}={want!r} vs event {field}={got!r}: "
                     f"{'ok' if ok else 'miss'}")
    return matched, parts


class FixtureJudge:
    """Deterministic stand-in for HugrGate HG-T4, same verdict schema."""

    judge_id = "fixture-judge-hg-t4-schema"

    def judge(self, declaration, event):
        matched, parts = _trigger_basis(declaration.trigger, event)
        basis = (f"trigger {'matched' if matched else 'not matched'}: "
                 + "; ".join(parts))
        return {"reflex": declaration.name, "fire": bool(matched),
                "basis": basis, "judge": self.judge_id}


class HugrGateJudge:
    """Live binding to HugrGate's reflex API (HG-T4).

    Swap-in for FixtureJudge once HG-T4 is banked; the live re-proof is
    owed until then. Any transport or protocol failure raises
    JudgeUnavailableError / MalformedVerdictError, which the binding
    turns into awareness-only degradation.
    """

    judge_id = "hugrgate-live"

    def __init__(self, endpoint, timeout=2.0):
        self.endpoint = endpoint
        self.timeout = timeout

    def judge(self, declaration, event):
        payload = json.dumps({
            "reflex": declaration.name,
            "trigger": declaration.trigger,
            "action": declaration.action,
            "event": event,
        }).encode()
        req = urllib.request.Request(
            self.endpoint, data=payload,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = json.loads(resp.read().decode())
        except Exception as e:
            raise JudgeUnavailableError(f"hugrgate unreachable: {e}") from e
        if not isinstance(raw, dict):
            raise MalformedVerdictError("hugrgate verdict is not an object")
        raw.setdefault("judge", self.judge_id)
        return raw


class JudgmentBinding:
    """Binds a ReflexRegistry to a judge; owns the degradation rule.

    `prefilter_unmatched=True` skips remote HugrGate judgment when an
    explicitly declared trigger is deterministically false. Matching events
    always require a valid judgment; any failed judge remains no-fire.
    """

    def __init__(self, registry, judge, logger=None, prefilter_unmatched=False):
        self.registry = registry
        self.judge = judge
        self.log = logger or log
        self.degraded = False
        self.degradation_log = []
        # Opt-in deterministic fast path. An event cannot fire a reflex
        # whose explicit declared trigger is false. Skip expensive HG-T4
        # calls for such cases; keep legacy judgment for matches and keep
        # the same one-verdict-per-reflex public API.
        self.prefilter_unmatched = bool(prefilter_unmatched)
        self.prefilter_count = 0
        self.judge_call_count = 0

    def _degrade(self, reflex_name, reason):
        self.degraded = True
        entry = f"judge degraded for reflex '{reflex_name}': {reason}"
        self.degradation_log.append(entry)
        self.log.error("Verdandi awareness-only: %s", entry)
        return Verdict(reflex=reflex_name, fire=False,
                       basis=f"no-fire: judge unavailable ({reason}); "
                             f"awareness-only, no reflex fires unjudged",
                       judge=getattr(self.judge, "judge_id", "unknown"),
                       degraded=True)

    def judge_one(self, reflex_name, event):
        decl = self.registry.require(reflex_name)
        if not decl.enabled:
            return Verdict(reflex=reflex_name, fire=False,
                           basis="no-fire: reflex declared disabled",
                           judge=getattr(self.judge, "judge_id", "unknown"))
        if self.prefilter_unmatched:
            matched, parts = _trigger_basis(decl.trigger, event)
            if not matched:
                self.prefilter_count += 1
                return Verdict(
                    reflex=reflex_name, fire=False,
                    basis="no-fire: declared trigger not matched: " + "; ".join(parts),
                    judge="deterministic-trigger-prefilter",
                )
        try:
            self.judge_call_count += 1
            raw = self.judge.judge(decl, event)
            verdict = _validate_verdict(raw, reflex_name)
            # An external judge must never substitute another reflex name:
            # only the exact declared candidate is permitted to fire.
            if verdict.reflex != reflex_name:
                raise MalformedVerdictError("judge returned a different reflex")
            return verdict
        except Exception as e:
            return self._degrade(reflex_name, f"{type(e).__name__}: {e}")

    def judge_event(self, event):
        """Verdicts for every declared reflex for one candidate event."""
        return [self.judge_one(name, event)
                for name in self.registry.names()]
