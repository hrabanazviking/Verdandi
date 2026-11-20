#!/usr/bin/env python3
"""Verdandi HugrGate judgment binding (VD-T2).

Verdandi sends candidate events to HugrGate's reflex API and receives
fire / no-fire with basis. The slice was first gated against a fixture
judge implementing the same verdict schema; the live binding below
(HugrGateJudge) speaks HG-T4's real wire protocol - register the
declaration with POST /reflexes, then judge with POST /reflex/judge -
and its live re-proof against the real decision server is recorded in
campaign/READINESS_PROGRESS.md (correction entry, 2026-11-20).

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
    """Deterministic stand-in for HugrGate HG-T4, same verdict schema.

    Kept as the semantics oracle for tests; live bindings use
    HugrGateJudge against the real server.
    """

    judge_id = "fixture-judge-hg-t4-schema"

    def judge(self, declaration, event):
        matched, parts = _trigger_basis(declaration.trigger, event)
        basis = (f"trigger {'matched' if matched else 'not matched'}: "
                 + "; ".join(parts))
        return {"reflex": declaration.name, "fire": bool(matched),
                "basis": basis, "judge": self.judge_id}


# Reserved adapter values: a Verdandi nerve event may carry no feed
# and no kind. HG-T4 judges only events with a source and a kind, so
# the adapter carries a missing feed/kind under these reserved values;
# no declared pattern matches them unless a consumer explicitly
# declares them (an adapter convention, not a judged fact).
RESERVED_SOURCE = "verdandi.unspecified"
RESERVED_KIND = "verdandi.unspecified"


def _pattern_from_trigger(trigger):
    """Translate a VD-T1 trigger dict into an HG-T4 pattern.

    feed -> source, kind -> kind ('*' means no constraint);
    '<field>_gte' / '_lte' / '_gt' / '_lt' -> a where comparison
    object; any other '<field>' -> a where equality ('*' means no
    constraint).
    """
    pattern = {}
    where = {}
    for key, want in trigger.items():
        if key in ("feed", "source"):
            if want != "*":
                pattern["source"] = want
            continue
        if key == "kind":
            if want != "*":
                pattern["kind"] = want
            continue
        field, op = key, None
        for suffix, name in (("_gte", "gte"), ("_lte", "lte"),
                             ("_gt", "gt"), ("_lt", "lt")):
            if key.endswith(suffix):
                field, op = key[:-len(suffix)], name
                break
        if op is not None:
            cond = dict(where.get(field, {}))
            cond[op] = want
            where[field] = cond
        elif want != "*":
            where[key] = want
    if where:
        pattern["where"] = where
    return pattern


def _event_for_hugrgate(event):
    """Translate a Verdandi nerve event into an HG-T4 event.

    source <- the event's own source, else its feed, else the reserved
    source; kind <- its kind, else the reserved kind; every remaining
    field rides in the payload, where HG-T4 patterns judge it.
    """
    payload = {}
    if isinstance(event.get("payload"), dict):
        payload.update(event["payload"])
    for k, v in event.items():
        if k not in ("feed", "source", "kind", "payload"):
            payload[k] = v
    return {
        "source": event.get("source") or event.get("feed") or RESERVED_SOURCE,
        "kind": event.get("kind") or RESERVED_KIND,
        "payload": payload,
    }


class HugrGateJudge:
    """Live binding to HugrGate's reflex API (HG-T4), real wire protocol.

    The server judges only DECLARED reflexes: this client registers
    each declaration (translated by _pattern_from_trigger) with
    POST /reflexes on first use, then sends each candidate event to
    POST /reflex/judge and reads back that reflex's verdict, basis
    included. If a response carries no verdict for the reflex (e.g.
    the server restarted and lost its registry), the client
    re-registers once and retries. Any transport or protocol failure
    raises JudgeUnavailableError / MalformedVerdictError, which the
    binding turns into awareness-only degradation.
    """

    judge_id = "hugrgate-live"

    def __init__(self, endpoint, timeout=2.0):
        base = str(endpoint).rstrip("/")
        for suffix in ("/reflex/judge", "/judge"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        self.base = base
        self.endpoint = base + "/reflex/judge"
        self.timeout = timeout
        self._registered = set()

    def _post(self, path, body):
        payload = json.dumps(body).encode()
        req = urllib.request.Request(
            self.base + path, data=payload,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            raise JudgeUnavailableError(f"hugrgate unreachable: {e}") from e

    def _register(self, declaration):
        body = {"name": declaration.name, "action": declaration.action,
                "pattern": _pattern_from_trigger(declaration.trigger),
                "consumer": "verdandi"}
        raw = self._post("/reflexes", body)
        if not isinstance(raw, dict) or "registered" not in raw:
            raise MalformedVerdictError(
                f"hugrgate refused reflex registration: {raw!r}")
        self._registered.add(declaration.name)

    def _judge_once(self, declaration, event):
        raw = self._post("/reflex/judge",
                         {"events": [_event_for_hugrgate(event)]})
        if not isinstance(raw, dict) \
                or not isinstance(raw.get("results"), list) \
                or not raw["results"]:
            raise MalformedVerdictError("hugrgate reflex verdict is malformed")
        for v in raw["results"][0].get("verdicts", []):
            if v.get("reflex") == declaration.name:
                return {"reflex": declaration.name, "fire": v.get("fire"),
                        "basis": v.get("basis"), "judge": self.judge_id}
        return None

    def judge(self, declaration, event):
        if declaration.name not in self._registered:
            self._register(declaration)
        verdict = self._judge_once(declaration, event)
        if verdict is None:
            self._register(declaration)
            verdict = self._judge_once(declaration, event)
        if verdict is None:
            raise MalformedVerdictError(
                f"hugrgate returned no verdict for reflex "
                f"{declaration.name!r}")
        return verdict


class JudgmentBinding:
    """Binds a ReflexRegistry to a judge; owns the degradation rule."""

    def __init__(self, registry, judge, logger=None):
        self.registry = registry
        self.judge = judge
        self.log = logger or log
        self.degraded = False
        self.degradation_log = []

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
        try:
            raw = self.judge.judge(decl, event)
            return _validate_verdict(raw, reflex_name)
        except Exception as e:
            return self._degrade(reflex_name, f"{type(e).__name__}: {e}")

    def judge_event(self, event):
        """Verdicts for every declared reflex for one candidate event."""
        return [self.judge_one(name, event)
                for name in self.registry.names()]
