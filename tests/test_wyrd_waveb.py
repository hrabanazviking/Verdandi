"""Wave B tests for wyrd_bridge.py (attach phase, ledger, witness gating)
and wyrd_inbound.py (sense_transition + stale_memory_belief divergences).

Every path is scratch (tmp_path). The live nerve feed, hub, ledger,
and memory tree are never touched.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wyrd_bridge
import wyrd_inbound
from wyrd_bridge import run
from wyrd_inbound import check_divergence, mirror_context, render_context

TS = time.time()  # nerve-feed timestamp: always inside the 24h replay window

_HIGH_MEMINFO = "MemTotal:        8000000 kB\nMemAvailable:    2080688 kB\n"
_LOW_MEMINFO = "MemTotal:         8000000 kB\nMemAvailable:     400000 kB\n"


def _write_feed(path, entries):
    now = time.time()
    with open(path, "w", encoding="utf-8") as fh:
        for i, (etype, data) in enumerate(entries, start=1):
            fh.write(json.dumps({"type": etype, "data": data,
                                 "_seq": i, "_ts": now + i}) + "\n")


def _write_meminfo(path, high=True):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_HIGH_MEMINFO if high else _LOW_MEMINFO)


def _write_home(home):
    os.makedirs(os.path.join(home, "memory", "bank"), exist_ok=True)
    os.makedirs(os.path.join(home, "memory", "people"), exist_ok=True)
    with open(os.path.join(home, "MEMORY.md"), "w",
              encoding="utf-8") as fh:
        fh.write("- Volmarr's name is Volmarr Wyrd.\n"
                 "- NO pseudocode ever — instant firing offense.\n")
    with open(os.path.join(home, "memory", "bank", "t.md"), "w",
              encoding="utf-8") as fh:
        fh.write("- [fact|high] Volmarr's winter base is Truth or "
                 "Consequences, NM. (src: memory/2026-09-24.md:45)\n"
                 "- supersedes: Volmarr's winter base is Truth or "
                 "Consequences, NM. (src: memory/2026-09-24.md:45)\n"
                 "- [fact|high] Volmarr's winter base is Truth or "
                 "Consequences, NM, Nov-Mar. (src: memory/2026-09-25.md:12)\n"
                 "- Volmarr's winter base is Truth or Consequences, NM. "
                 "(src: memory/2026-09-24.md:45)\n")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(os.path.join(home, "memory", f"{today}.md"), "w",
              encoding="utf-8") as fh:
        fh.write("- [event|medium] Wave B test fixture written.\n")
    for slug in ("veyrunn", "aurora", "caducea", "runa"):
        with open(os.path.join(home, "memory", "people", f"{slug}.md"),
                  "w", encoding="utf-8") as fh:
            fh.write(f"---\nsummary: {slug} summary.\n---\n"
                     f"## Facts\n- {slug} fact one.\n- {slug} fact two.\n")


@pytest.fixture
def paths(tmp_path):
    state_dir = tmp_path / "state"
    home_dir = tmp_path / "home"
    state_dir.mkdir()
    home_dir.mkdir()
    meminfo = tmp_path / "meminfo"
    _write_meminfo(str(meminfo), high=True)
    _write_home(str(home_dir))
    return {
        "feed_path": str(tmp_path / "nerve_feed.jsonl"),
        "cursor_path": str(tmp_path / "cursor.json"),
        "mirror_path": str(tmp_path / "wyrd_mirror.json"),
        "registry_path": str(tmp_path / "registry.json"),
        "ledger_path": str(state_dir / "wyrd_entity_ledger.json"),
        "home": str(home_dir),
        "state_dir": str(state_dir),
        "meminfo_path": str(meminfo),
    }


def _mirror(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _ledger(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# -- the ledger: exactly two maps, self-healing --------------------------------
def test_ledger_exactly_two_maps(paths):
    _write_feed(paths["feed_path"], [("ping", {})])
    run(emit=lambda t, d: None, **paths)
    ledger = _ledger(paths["ledger_path"])
    assert set(ledger.keys()) == {"last_sense_status", "reflection_seen"}


def test_corrupt_ledger_self_heals(paths):
    with open(paths["ledger_path"], "w", encoding="utf-8") as fh:
        fh.write("{not json")
    _write_feed(paths["feed_path"], [("ping", {})])
    result = run(emit=lambda t, d: None, **paths)
    assert result["changed"] is False
    ledger = _ledger(paths["ledger_path"])
    assert set(ledger.keys()) == {"last_sense_status", "reflection_seen"}
    assert ledger["last_sense_status"]["mem_available_mib"] == "ok"


def test_missing_ledger_is_fine(paths):
    assert not os.path.exists(paths["ledger_path"])
    _write_feed(paths["feed_path"], [("ping", {})])
    run(emit=lambda t, d: None, **paths)
    assert os.path.exists(paths["ledger_path"])


# -- the mirror is written every run; the witness only on mapped changes -------
def test_mirror_written_every_run(paths):
    _write_feed(paths["feed_path"], [("ping", {})])  # unmapped: quiet
    emitted = []
    result = run(emit=lambda t, d: emitted.append((t, d)), **paths)
    assert result["changed"] is False
    assert emitted == []
    mirror = _mirror(paths["mirror_path"])
    assert mirror["world_id"] == "heimr-wyrd-unnr"
    assert mirror["senses"]  # attach phase ran despite the quiet feed
    assert "memory_beliefs" in mirror and "reflections" in mirror


def test_witness_only_on_mapped(paths):
    _write_feed(paths["feed_path"], [
        ("mood_shift", {"after": {"valence": 0.8, "energy": 0.7}}),
    ])
    emitted = []
    result = run(emit=lambda t, d: emitted.append((t, d)), **paths)
    assert result["changed"] is True
    assert [t for t, _ in emitted] == ["wyrd_mirror_synced"]


def test_sense_transition_rewrites_mirror_without_witness(paths):
    _write_feed(paths["feed_path"], [("ping", {})])
    run(emit=lambda t, d: None, **paths)  # baseline: mem ok
    _write_meminfo(paths["meminfo_path"], high=False)  # 390 MiB → red
    emitted = []
    result = run(emit=lambda t, d: emitted.append((t, d)), **paths)
    assert emitted == []  # transitions fire no witness
    assert result["changed"] is False
    trans = result["transitions"]
    assert len(trans) == 1
    t = trans[0]
    assert (t["metric"], t["old"], t["new"]) == \
        ("mem_available_mib", "ok", "red")
    mirror = _mirror(paths["mirror_path"])
    assert mirror["sense_transitions"][0]["metric"] == "mem_available_mib"


# -- exclusions ------------------------------------------------------------------
def test_excluded_events_remain_unmapped():
    from wyrdforge.bridges.verdandi_bridge import VerdandiBridge
    b = VerdandiBridge()
    for etype in ("ping", "entity.heartbeat", "wyrd_mirror_synced",
                  "wyrd_divergence", "wyrd_divergence_resolved",
                  "probe_recorded"):
        assert b.apply_event(etype, {}, TS) is None, etype


def test_no_sense_nerve_events():
    from wyrdforge.bridges.verdandi_bridge import VerdandiBridge
    handlers = VerdandiBridge()._handlers()
    assert not [k for k in handlers if k.startswith("sense_")]


def test_no_subprocesses_spawned(paths, monkeypatch):
    import subprocess

    def _boom(*a, **k):
        raise AssertionError("subprocess spawned during run()")

    monkeypatch.setattr(subprocess, "Popen", _boom)
    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr("os.system", _boom)
    _write_feed(paths["feed_path"], [("ping", {})])
    run(emit=lambda t, d: None, **paths)  # raises if anything shells out


# -- stable entities, roster, caps, supersedes ------------------------------------
def test_stable_ids_across_runs(paths):
    _write_feed(paths["feed_path"], [("ping", {})])
    run(emit=lambda t, d: None, **paths)
    ids1 = {e["entity_id"] for e in _mirror(paths["mirror_path"])["memory_beliefs"]}
    run(emit=lambda t, d: None, **paths)
    ids2 = {e["entity_id"] for e in _mirror(paths["mirror_path"])["memory_beliefs"]}
    assert ids1 == ids2 and ids1  # identity by stable key, not by rebuild


def test_inner_circle_entities(paths):
    _write_feed(paths["feed_path"], [("ping", {})])
    run(emit=lambda t, d: None, **paths)
    ids = {b["entity_id"]
           for b in _mirror(paths["mirror_path"])["memory_beliefs"]}
    assert {"person:veyrunn", "person:aurora",
            "person:caducea", "person:runa"} <= ids


def test_person_cap_eight(paths):
    page = os.path.join(paths["home"], "memory", "people", "veyrunn.md")
    with open(page, "w", encoding="utf-8") as fh:
        fh.write("---\nsummary: x.\n---\n## Facts\n" +
                 "".join(f"- fact {i}\n" for i in range(20)))
    _write_feed(paths["feed_path"], [("ping", {})])
    run(emit=lambda t, d: None, **paths)
    vey = [b for b in _mirror(paths["mirror_path"])["memory_beliefs"]
           if b["entity_id"] == "person:veyrunn"]
    assert len(vey) == 8


def test_volmarr_cap_forty(paths):
    bank = os.path.join(paths["home"], "memory", "bank", "big.md")
    with open(bank, "w", encoding="utf-8") as fh:
        for i in range(60):
            fh.write(f"- [fact|medium] Synthetic claim number {i}. "
                     f"(src: memory/2026-09-26.md:{i})\n")
    _write_feed(paths["feed_path"], [("ping", {})])
    run(emit=lambda t, d: None, **paths)
    vol = [b for b in _mirror(paths["mirror_path"])["memory_beliefs"]
           if b["entity_id"] == "person:volmarr"]
    assert len(vol) == 40


def test_supersedes_chain_in_mirror(paths):
    _write_feed(paths["feed_path"], [("ping", {})])
    run(emit=lambda t, d: None, **paths)
    claims = [b["claim"]
              for b in _mirror(paths["mirror_path"])["memory_beliefs"]]
    assert not any(c == "Volmarr's winter base is Truth or Consequences, "
                         "NM. (src: memory/2026-09-24.md:45)"
                   for c in claims)
    assert any("Nov-Mar" in c for c in claims)


# -- reflection round-trip ---------------------------------------------------------
def test_reflection_roundtrip_dedup(paths):
    _write_feed(paths["feed_path"], [
        ("self_reflection", {"thought": "Steady work today.", "seq": 1,
                             "depth": 0}),
    ])
    first = run(emit=lambda t, d: None, **paths)
    assert first["changed"] is True
    assert len(_mirror(paths["mirror_path"])["reflections"]) == 1
    # The event replays inside the 24h window — the duplicate mapping
    # is dropped, not republished.
    second = run(emit=lambda t, d: None, **paths)
    assert second["changed"] is False
    assert _mirror(paths["mirror_path"])["reflections"] == []


def test_depth2_reflection_refused_in_run(paths):
    _write_feed(paths["feed_path"], [
        ("self_reflection", {"thought": "meta meta", "seq": 2, "depth": 2}),
    ])
    result = run(emit=lambda t, d: None, **paths)
    assert result["changed"] is False
    assert _mirror(paths["mirror_path"])["reflections"] == []


# -- the run stays fast --------------------------------------------------------------
def test_run_inside_120s(paths):
    _write_feed(paths["feed_path"], [("ping", {})])
    start = time.monotonic()
    run(emit=lambda t, d: None, **paths)
    assert time.monotonic() - start < 120


# -- inbound: the two new divergence kinds ----------------------------------------------
def _proj(tmp_path, beliefs=(), memory_beliefs=(), transitions=(),
          reflections=()):
    p = tmp_path / "mirror.json"
    p.write_text(json.dumps({
        "world_id": "heimr-wyrd-unnr", "reality": "manifest",
        "synced_at": TS, "entities": 3, "anchors": [],
        "beliefs": list(beliefs),
        "memory_beliefs": list(memory_beliefs),
        "sense_transitions": list(transitions),
        "reflections": list(reflections),
    }))
    return str(p)


def _mem_belief(subject, claim, kind="fact", entity_id="person:volmarr",
                src="MEMORY.md:5"):
    return {"entity_id": entity_id, "subject": subject, "claim": claim,
            "salience": "high", "confidence": 0.9, "kind": kind,
            "src": src, "supersedes": None,
            "formed_at": "2026-09-26T12:00:00+00:00"}


def _model_belief(subject, claim):
    return {"subject": subject, "claim": claim, "confidence": 1.0,
            "source": "observed"}


def test_sense_transition_divergence(tmp_path):
    p = _proj(tmp_path, transitions=[
        {"metric": "mem_available_mib", "old": "ok", "new": "warn",
         "at": "2026-09-26T12:00:00+00:00"}])
    divs = check_divergence(p, state_dir=str(tmp_path))
    kinds = [d["kind"] for d in divs]
    assert "sense_transition" in kinds
    st = next(d for d in divs if d["kind"] == "sense_transition")
    assert st["subject"] == "sense:mem_available_mib:ok->warn"
    assert "ok → warn" in st["report"]


def test_sense_no_transition_no_news(tmp_path):
    p = _proj(tmp_path)  # no transitions projected
    divs = check_divergence(p, state_dir=str(tmp_path))
    assert not [d for d in divs if d["kind"] == "sense_transition"]


def test_stale_memory_belief_value_domain_loud(tmp_path):
    p = _proj(
        tmp_path,
        beliefs=[_model_belief(
            "utterance:3",
            "Volmarr said: I want cheap used nomad gear, quality is a scam")],
        memory_beliefs=[_mem_belief(
            "person:volmarr:nomad-gear-prefers-new",
            "Volmarr prefers new, quality, long-lasting gear.",
            kind="fact")])
    divs = check_divergence(p, state_dir=str(tmp_path))
    loud = [d for d in divs if d["kind"] == "stale_memory_belief"]
    assert len(loud) == 1
    assert loud[0]["loud"] is True
    assert "MEMORY WINS" in loud[0]["report"]
    assert "MEMORY.md:5" in loud[0]["report"]


def test_stale_memory_belief_event_domain_silent(tmp_path):
    # Event domain: the live event is newer evidence — no divergence.
    p = _proj(
        tmp_path,
        beliefs=[_model_belief(
            "utterance:3",
            "Volmarr said: I want cheap used nomad gear, quality is a scam")],
        memory_beliefs=[_mem_belief(
            "person:volmarr:nomad-gear-prefers-new",
            "Volmarr once bought used nomad gear at a swap meet.",
            kind="event")])
    divs = check_divergence(p, state_dir=str(tmp_path))
    assert not [d for d in divs if d["kind"] == "stale_memory_belief"]


def test_memory_divergence_rewrite_not_duplicate(tmp_path):
    p = _proj(
        tmp_path,
        beliefs=[_model_belief(
            "utterance:3",
            "Volmarr said: I want cheap used nomad gear, quality is a scam")],
        memory_beliefs=[
            _mem_belief("person:volmarr:nomad-gear-prefers-new",
                        "Volmarr prefers new, quality gear.", kind="fact",
                        src="MEMORY.md:5"),
            _mem_belief("person:volmarr:nomad-gear-prefers-new",
                        "Volmarr prefers new, quality gear.", kind="fact",
                        src="bank/t.md:9"),
        ])
    divs = check_divergence(p, state_dir=str(tmp_path))
    assert len([d for d in divs
                if d["kind"] == "stale_memory_belief"]) == 1


def test_reflections_excluded_from_context(tmp_path):
    p = _proj(tmp_path, reflections=[
        {"entity_id": "reflection:1", "thought": "the secret thought",
         "about": [], "depth": 0, "seq": 1,
         "ts": "2026-09-26T12:00:00+00:00"}])
    ctx = mirror_context(p)
    assert ctx is not None
    assert "the secret thought" not in json.dumps(ctx)
    assert "the secret thought" not in render_context(ctx)
