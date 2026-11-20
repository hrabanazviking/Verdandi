"""VD-T2 LIVE re-proof (2026-11-20 correction): the binding judged by
the REAL HugrGate decision server (HG-T4 reflex API) over real HTTP.

No fixture judge anywhere in the proof path. FixtureJudge appears only
as the semantics oracle the live verdicts are cross-checked against;
the expected fires table below is hand-derived from the VD-T1 first
set's declarations. The server is the banked HugrGate implementation,
started on an ephemeral localhost port with its judgment ledger on.
"""
import json
import os
import sys
from pathlib import Path

import pytest

from reflexes import ReflexRegistry
from reflex_judgment import FixtureJudge, HugrGateJudge, JudgmentBinding

FIX = Path(__file__).parent / "fixtures"

HUGRGATE_DIR = Path(os.environ.get(
    "HUGRGATE_READINESS_DIR",
    Path.home() / "forges" / "hugrgate-readiness"))
if str(HUGRGATE_DIR) not in sys.path:
    sys.path.insert(0, str(HUGRGATE_DIR))

hugrgate_server = pytest.importorskip("hugrgate.decision_server")
DecisionServer = hugrgate_server.DecisionServer

# Hand-derived from the VD-T1 first set: the reflex that fires for
# each event of the recorded nerve stream, in stream order.
EXPECTED_FIRES = [
    ["spike-notify"],   # wyrd, salience 0.95 >= 0.8
    [],                 # wyrd, salience 0.3
    ["threat-brace"],   # threat 0.9 >= 0.7
    [],                 # threat 0.2
    ["noisy-shed"],     # noise 0.97 >= 0.9
    [],                 # noise 0.4
    ["stalled-wake"],   # status stalled
    [],                 # status running
    ["alert-speak"],    # kind alert
    [],                 # kind note
    [],                 # quiet, salience 0.1
]


@pytest.fixture()
def live_server(tmp_path):
    srv = DecisionServer(host="127.0.0.1", port=0,
                         ledger_path=str(tmp_path / "ledger.jsonl"))
    srv.start()
    try:
        yield srv
    finally:
        srv.stop()


def _registry():
    return ReflexRegistry.load(FIX / "reflex_first_set_fixture.json")


def _binding(srv):
    judge = HugrGateJudge(f"http://127.0.0.1:{srv.address[1]}")
    return JudgmentBinding(_registry(), judge)


def test_live_binding_fires_exactly_the_declared_table(live_server):
    events = json.loads(
        (FIX / "reflex_event_stream_fixture.json").read_text())["events"]
    binding = _binding(live_server)
    oracle = JudgmentBinding(_registry(), FixtureJudge())
    for event, expected in zip(events, EXPECTED_FIRES):
        verdicts = binding.judge_event(event)
        assert binding.degraded is False and binding.degradation_log == []
        assert [v.reflex for v in verdicts if v.fire] == expected
        assert all(v.judge == "hugrgate-live" for v in verdicts)
        assert all(v.basis.strip() for v in verdicts)
        oracle_verdicts = oracle.judge_event(event)
        assert [v.fire for v in verdicts] == [v.fire for v in oracle_verdicts]
    status = live_server.ledger_status()
    assert status["enabled"] and status["verified"]
    # Every server verdict is ledgered. The client asks per reflex and
    # the server judges (and ledgers) every registered reflex per
    # call: event 1 ledgers 1+2+3+4+5 as registrations land one by
    # one, events 2-11 ledger 5 calls x 5 verdicts each.
    assert status["entries"] == 15 + 10 * 25


def test_live_binding_degrades_when_the_real_server_dies(live_server):
    binding = _binding(live_server)
    event = {"feed": "wyrd", "salience": 0.95}
    v = binding.judge_one("spike-notify", event)
    assert v.fire is True and v.degraded is False
    live_server.stop()
    v = binding.judge_one("spike-notify", event)
    assert v.fire is False and v.degraded is True
    assert binding.degraded is True and len(binding.degradation_log) == 1
