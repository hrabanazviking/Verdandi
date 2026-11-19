import logging
import pytest
from reflexes import ReflexRegistry, UnknownReflexError
from reflex_judgment import (FixtureJudge, HugrGateJudge, JudgmentBinding,
                             JudgeUnavailableError, Verdict)

REG = {"reflexes": [
    {"name": "feed-spike-notify",
     "trigger": {"feed": "wyrd", "salience_gte": 0.8},
     "action": "notify", "params": {"channel": "awareness"},
     "rate_limit_per_minute": 6, "owner_grant": "volmarr-2026-11-18"},
    {"name": "noisy-source-shed",
     "trigger": {"feed": "*", "noise_gte": 0.9},
     "action": "shed", "params": {"summary_rate_seconds": 60},
     "rate_limit_per_minute": 2, "owner_grant": "volmarr-2026-11-18",
     "enabled": False},
]}
MATCH = {"feed": "wyrd", "salience": 0.95}
NO_MATCH = {"feed": "wyrd", "salience": 0.3}


def binding(judge=None):
    return JudgmentBinding(ReflexRegistry.from_dict(REG),
                           judge or FixtureJudge())


def test_fixture_judge_fires_with_basis():
    v = binding().judge_one("feed-spike-notify", MATCH)
    assert isinstance(v, Verdict)
    assert v.fire is True and v.degraded is False
    assert v.judge == "fixture-judge-hg-t4-schema"
    assert "salience_gte" in v.basis and "matched" in v.basis


def test_fixture_judge_no_fire_with_basis():
    v = binding().judge_one("feed-spike-notify", NO_MATCH)
    assert v.fire is False and v.degraded is False
    assert "not matched" in v.basis and v.basis.strip()


def test_judge_event_covers_all_declared():
    vs = binding().judge_event(MATCH)
    assert [v.reflex for v in vs] == ["feed-spike-notify", "noisy-source-shed"]
    assert vs[0].fire is True
    assert vs[1].fire is False and "disabled" in vs[1].basis


def test_undeclared_reflex_is_never_judged():
    with pytest.raises(UnknownReflexError):
        binding().judge_one("ghost", MATCH)


class DeadJudge:
    judge_id = "dead-judge"

    def judge(self, declaration, event):
        raise JudgeUnavailableError("connection refused")


def test_dead_judge_degrades_awareness_only_and_logs(caplog):
    b = binding(DeadJudge())
    with caplog.at_level(logging.ERROR, logger="verdandi.reflex_judgment"):
        v = b.judge_one("feed-spike-notify", MATCH)
    assert v.fire is False and v.degraded is True
    assert b.degraded is True and len(b.degradation_log) == 1
    assert "awareness-only" in caplog.text


class MalformedJudge:
    judge_id = "malformed-judge"

    def judge(self, declaration, event):
        return {"fire": "yes"}


def test_malformed_verdict_degrades_never_fires():
    b = binding(MalformedJudge())
    v = b.judge_one("feed-spike-notify", MATCH)
    assert v.fire is False and v.degraded is True and b.degraded is True


def test_dead_live_judge_degrades_never_fires():
    judge = HugrGateJudge("http://127.0.0.1:1/judge", timeout=0.5)
    b = binding(judge)
    v = b.judge_one("feed-spike-notify", MATCH)
    assert v.fire is False and v.degraded is True
