import json
from pathlib import Path
import pytest
from reflexes import (ReflexRegistry, MalformedDeclarationError,
                      DuplicateReflexError, UngrantedReflexError, UnknownReflexError)

FIXTURE = Path(__file__).parent / "fixtures" / "reflex_registry_fixture.json"
GOOD = {"name": "a-reflex", "trigger": {"feed": "x"}, "action": "notify",
        "rate_limit_per_minute": 3, "owner_grant": "volmarr"}

def test_fixture_loads_exactly_as_written():
    reg = ReflexRegistry.load(FIXTURE)
    assert reg.names() == ["feed-spike-notify", "noisy-source-shed"]
    d = reg.require("feed-spike-notify")
    assert d.trigger == {"feed": "wyrd", "salience_gte": 0.8}
    assert d.action == "notify" and d.params == {"channel": "awareness"}
    assert d.rate_limit_per_minute == 6 and d.owner_grant == "volmarr-2026-11-18"
    assert reg.require("noisy-source-shed").enabled is False

def test_malformed_rejected_named():
    for bad in [{}, {"name": "X Bad!"}, {**GOOD, "trigger": {}}, {**GOOD, "action": ""},
                {**GOOD, "rate_limit_per_minute": 0}, {**GOOD, "params": []}, "nope"]:
        with pytest.raises(MalformedDeclarationError):
            ReflexRegistry.from_dict([bad])

def test_duplicate_rejected_named():
    with pytest.raises(DuplicateReflexError):
        ReflexRegistry.from_dict([GOOD, dict(GOOD)])

def test_ungranted_rejected_named():
    for bad in [{k: v for k, v in GOOD.items() if k != "owner_grant"},
                {**GOOD, "owner_grant": ""}, {**GOOD, "owner_grant": False}]:
        with pytest.raises(UngrantedReflexError):
            ReflexRegistry.from_dict([bad])

def test_undeclared_reflex_does_not_exist():
    reg = ReflexRegistry.from_dict([GOOD])
    assert "ghost" not in reg and reg.get("ghost") is None
    with pytest.raises(UnknownReflexError):
        reg.require("ghost")

def test_bad_file_rejected_named(tmp_path):
    p = tmp_path / "r.json"; p.write_text("{not json")
    with pytest.raises(MalformedDeclarationError):
        ReflexRegistry.load(p)
