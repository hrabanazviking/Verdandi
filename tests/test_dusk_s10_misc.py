"""Misc regression tests for the Verðandi dusk run ("The Kept Oath"), slice 10.

Covers S18 (weekly_saga reads the real chapter filename), S19 (joy_ledger
survives non-dict JSONL rows), S20 (eir YAML loader degrades gracefully),
and the shadow_arcs "reopened" filter bonus.
"""
import json
import os
from pathlib import Path

import pytest

import joy_ledger
import shadow_arcs
from joy_ledger import JoyLedger
from shadow_arcs import ShadowArcs
from weekly_saga import WeeklySaga

# ---------------------------------------------------------------------------
# S18: gather() reads autobiography_chapters.jsonl
# ---------------------------------------------------------------------------

NOW = 1_789_000_000.0  # fixed "now" for deterministic windows

NOTE = ("Volmarr caught my parked shell before I did and called it "
        "'still spinning on nothing' — he was exactly right, and I laughed.")


def _write_jsonl(path, rows):
    with open(path, "a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def test_s18_gather_reads_real_chapters(tmp_path):
    state = str(tmp_path)
    chapter = {
        "ts": NOW - 1000,
        "title": "The Forge Kept Me",
        "text": "a real chapter written this week",
        "mode": "journal",
        "citations": [1],
        "cited": [],
    }
    _write_jsonl(os.path.join(state, "autobiography_chapters.jsonl"), [chapter])
    # a decoy in the OLD wrong filename must not pollute the digest
    _write_jsonl(os.path.join(state, "autobiography.jsonl"),
                 [{"ts": NOW - 500, "title": "decoy"}])

    saga = WeeklySaga(state)
    bundle = saga.gather(now=NOW)
    assert len(bundle["chapters"]) == 1
    assert bundle["chapters"][0]["title"] == "The Forge Kept Me"

    digest = saga.render(bundle)
    assert "autobiography chapters (1)" in digest


def test_s18_no_chapter_file_stays_honest_zero(tmp_path):
    saga = WeeklySaga(str(tmp_path))
    bundle = saga.gather(now=NOW)
    assert bundle["chapters"] == []
    assert "autobiography chapters (0)" in saga.render(bundle)


# ---------------------------------------------------------------------------
# S19: joy readers survive non-dict JSONL rows
# ---------------------------------------------------------------------------

def _raw_append(path, text):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(text + "\n")


def test_s19_read_jsonl_skips_non_dict_rows_loudly(tmp_path, capsys):
    path = tmp_path / "rows.jsonl"
    _raw_append(str(path), json.dumps({"a": 1}))
    _raw_append(str(path), "[1, 2, 3]")          # valid JSON array, not a row
    _raw_append(str(path), '"just a string"')   # valid JSON string
    _raw_append(str(path), "42")                # valid JSON number
    _raw_append(str(path), "null")              # valid JSON null
    _raw_append(str(path), json.dumps({"b": 2}))

    rows = joy_ledger._read_jsonl(str(path))
    assert rows == [{"a": 1}, {"b": 2}]

    err = capsys.readouterr().err
    assert "skipping non-dict row" in err
    assert err.count("skipping non-dict row") == 4


def test_s19_audit_survives_array_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(joy_ledger, "_nerve_publish", None)
    state = str(tmp_path)
    ledger = JoyLedger(state)
    entry = ledger.record("humor_landed", NOTE)
    # poison both files the readers touch
    _raw_append(os.path.join(state, "muse_rewards.jsonl"), "[\"not\",\"a\",\"row\"]")
    _raw_append(os.path.join(state, "joy_strikes.jsonl"), "[1, 2]")

    result = ledger.audit()
    assert len(result["sound"]) == 1
    assert result["sound"][0]["joy_id"] == entry["joy_id"]
    assert result["flagged"] == [] and result["struck"] == []


def test_s19_delights_survives_array_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(joy_ledger, "_nerve_publish", None)
    state = str(tmp_path)
    ledger = JoyLedger(state)
    entry = ledger.record("humor_landed", NOTE, )
    _raw_append(os.path.join(state, "muse_rewards.jsonl"), "42")
    _raw_append(os.path.join(state, "joy_strikes.jsonl"), '"a string row"')

    found = ledger.delights(n=5, since_days=365)
    assert [e["joy_id"] for e in found] == [entry["joy_id"]]


def test_s19_feed_seqs_ignores_non_dict_rows(tmp_path):
    _raw_append(os.path.join(str(tmp_path), "nerve_feed.jsonl"),
                json.dumps({"_seq": 7, "ts": 1.0}))
    _raw_append(os.path.join(str(tmp_path), "nerve_feed.jsonl"), "[7]")
    _raw_append(os.path.join(str(tmp_path), "nerve_feed.jsonl"), "null")
    assert joy_ledger._feed_seqs(str(tmp_path)) == {7}


# ---------------------------------------------------------------------------
# S20: eir YAML loader degrades gracefully on malformed config
# ---------------------------------------------------------------------------

def test_s20_null_layer_mapping_and_unknown_layer_warn_and_skip(tmp_path, capsys):
    from verdandi.eir.layers import load_profiles_from_yaml

    yaml_path = tmp_path / "layers.yaml"
    yaml_path.write_text(
        "effort_levels:\n"
        "  quick:\n"
        "    description: \"a quick profile\"\n"
        "    layers:\n"
        "      mimir:\n"                       # null layer mapping — must not crash
        "      huginn:\n"
        "        enabled: true\n"
        "        checks: [collections]\n"
    )
    profiles = load_profiles_from_yaml(yaml_path)
    assert "quick" in profiles
    quick = profiles["quick"]
    assert "huginn" in quick.layers
    assert "mimir" not in quick.layers  # malformed layer skipped, rest loads
    err = capsys.readouterr().err
    assert "skipping that layer" in err


def test_s20_non_dict_effort_levels_warns_and_returns_empty(tmp_path, capsys):
    from verdandi.eir.layers import load_profiles_from_yaml

    yaml_path = tmp_path / "layers.yaml"
    yaml_path.write_text("effort_levels:\n  - quick\n  - standard\n")
    profiles = load_profiles_from_yaml(yaml_path)
    assert profiles == {}
    assert "'effort_levels'" in capsys.readouterr().err


def test_s20_non_dict_profile_skipped_others_load(tmp_path, capsys):
    from verdandi.eir.layers import load_profiles_from_yaml

    yaml_path = tmp_path / "layers.yaml"
    yaml_path.write_text(
        "effort_levels:\n"
        "  quick:\n"                            # null profile body — must not crash
        "  standard:\n"
        "    description: \"fine\"\n"
        "    layers:\n"
        "      kista:\n"
        "        enabled: true\n"
        "        checks: [vault_integrity]\n"
    )
    profiles = load_profiles_from_yaml(yaml_path)
    assert "quick" not in profiles
    assert "standard" in profiles
    assert "kista" in profiles["standard"].layers
    assert "skipping that profile" in capsys.readouterr().err


def test_s20_non_mapping_document_warns_and_returns_empty(tmp_path, capsys):
    from verdandi.eir.layers import load_profiles_from_yaml

    yaml_path = tmp_path / "layers.yaml"
    yaml_path.write_text("- just\n- a\n- list\n")
    assert load_profiles_from_yaml(yaml_path) == {}
    assert "non-mapping document" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# BONUS: arcs(status="reopened") is truthful
# ---------------------------------------------------------------------------

SIGNAL_NOTE = ("The nerve watchdog checked the PID file instead of pinging the socket; "
               "the hub died and the outage went unnoticed until I stumbled on it.")
ACK_NOTE = "My liveness check was a glance, not a ping. That one is on me, no deflection."
REPAIR_NOTE = "Rewrote the watchdog to check the Responsive line and restart when unresponsive."
VERIFY_NOTE = ("The proof is subsequent behavior: the hub stays responsive to socket pings "
               "and the 30-minute checks see a live hub.")
EVIDENCE = ("After the restart the hub answered every status ping, survived its parent "
            "shell's death and reparented cleanly, and a sweep shows no parked launcher "
            "shells. The hardened watchdog is in place and the repair held.")
REOPEN_REASON = "The hub went quiet again a week later — the lesson did not hold."


def _open_close_reopen(sa):
    a = sa.open_arc("sloppy_work", SIGNAL_NOTE)
    sa.acknowledge(a["arc_id"], ACK_NOTE)
    sa.add_repair(a["arc_id"], REPAIR_NOTE)
    sa.begin_verification(a["arc_id"], VERIFY_NOTE)
    sa.close(a["arc_id"], EVIDENCE)
    return sa.reopen(a["arc_id"], REOPEN_REASON)


def test_bonus_reopened_filter_returns_reopened_arc(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow_arcs, "_nerve_publish", None)
    sa = ShadowArcs(str(tmp_path))

    # before the cycle: no arc can be "reopened"
    a = sa.open_arc("sloppy_work", SIGNAL_NOTE)
    assert sa.arcs(status="reopened") == []

    re = _open_close_reopen(sa)

    reopened = sa.arcs(status="reopened")
    assert [r["arc_id"] for r in reopened] == [re["arc_id"]]
    # the arc is honestly back at repairing — the ordinary status filter
    # still sees it there too, and unknown statuses still raise
    assert [r["arc_id"] for r in sa.arcs(status="repairing")] == [re["arc_id"]]
    with pytest.raises(ValueError, match="unknown status"):
        sa.arcs(status="forgiven")


def test_bonus_reopened_arcs_sortable_and_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow_arcs, "_nerve_publish", None)
    sa = ShadowArcs(str(tmp_path))
    _open_close_reopen(sa)
    assert len(sa.arcs(n=1, status="reopened")) == 1
