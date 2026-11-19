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


def _wyrdforge_importable():
    try:
        import wyrdforge  # noqa: F401
        return True
    except ImportError:
        return False


_WYRD_AVAILABLE = _wyrdforge_importable()

# Tests that need the REAL wyrdforge backend skip while the WYRD repo is
# absent. All the run()-based tests below exercise wyrd_bridge's
# decoupled logic through the fake_wyrdforge test double instead and
# run regardless.
requires_wyrdforge = pytest.mark.skipif(not _WYRD_AVAILABLE,
                                        reason="WYRD repo absent")


def _build_fake_wyrdforge():
    """Minimal wyrdforge test double — same surface contract as the one
    in test_wyrd_bridge.py (duplicated deliberately so each test file is
    self-contained): the VerdandiBridge class, the vb constants and the
    vb functions parse_memory_beliefs/sample_senses/environment_facts.
    A test double, not the real backend — faithful enough that stable
    IDs, mapping, supersedes chains, transition detection, ledger shape
    and witness gating are genuinely exercised."""
    import hashlib
    import re
    import types
    from datetime import datetime, timezone
    from types import SimpleNamespace

    vb = types.ModuleType("wyrdforge.bridges.verdandi_bridge")
    vb.__doc__ = "Test double for wyrdforge.bridges.verdandi_bridge."

    vb.VOLMARR_ID = "person:volmarr"
    vb.PERSON_ROSTER = ("veyrunn", "aurora", "caducea", "runa")
    vb.MACHINE_ID = "env:machine"
    vb.RHYTHM_ID = "env:rhythm"
    vb.PLACE_ANGOLA_ID = "env:place-angola"
    vb.PLACE_TORC_ID = "env:place-torc"

    _UNMAPPED = {"ping", "entity.heartbeat", "wyrd_mirror_synced",
                 "wyrd_divergence", "wyrd_divergence_resolved",
                 "probe_recorded"}

    class _FakeWorld:
        def __init__(self):
            self.world_id = "heimr-wyrd-unnr"
            self.identity = SimpleNamespace(reality="manifest")

        def registry_entry(self):
            return {"world_id": self.world_id, "kind": "wyrd",
                    "reality": "manifest", "source": "wyrd_bridge",
                    "description": "WYRD mirror world (test double)",
                    "status": "active"}

    class VerdandiBridge:
        def __init__(self, ledger=None):
            self._ledger = ledger if ledger is not None else {}
            self._entities = {}
            self._anchors = []
            self._beliefs = []
            self._memory_beliefs = []
            self._reflections = []
            self._senses = []
            self._transitions = []
            self._env = {}
            self.world = _FakeWorld()

        def ensure_entity(self, entity_id, kinds):
            self._entities.setdefault(entity_id, set()).update(kinds)

        def _handlers(self):
            return {"mood_shift": self._map_mood,
                    "wish_made": self._map_wish,
                    "self_reflection": self._map_reflection}

        def apply_event(self, etype, data, ts):
            if etype in _UNMAPPED:
                return None
            handler = self._handlers().get(etype)
            if handler is None:
                return None
            return handler(data or {}, ts)

        def _anchor(self, label, tense, at):
            self._anchors.append({"label": label, "tense": tense,
                                  "at": at, "tags": []})

        def _map_mood(self, data, ts):
            after = data.get("after", {}) or {}
            valence = after.get("valence", 0.0)
            self._beliefs.append(
                {"subject": "unnr:mood",
                 "claim": f"my valence sits at {valence}",
                 "confidence": 1.0, "source": "observed"})
            self._anchor(f"mood shift (valence {valence})", "verdhandi", ts)
            return f"mapped mood_shift (valence {valence})"

        def _map_wish(self, data, ts):
            wid = data.get("wish_id", "?")
            text = data.get("text", "")
            self._beliefs.append(
                {"subject": f"wish:{wid}",
                 "claim": f"I want this: {text}",
                 "confidence": 1.0, "source": "observed"})
            self._anchor(f"wish made: {text}", "verdhandi", ts)
            return f"mapped wish_made {wid}"

        def _map_reflection(self, data, ts):
            thought = str(data.get("thought", ""))
            seq = data.get("seq")
            try:
                depth = int(data.get("depth", 0) or 0)
            except (TypeError, ValueError):
                depth = 0
            if depth >= 2:
                return None  # depth cap: meta-reflections are refused
            digest = hashlib.sha1(
                f"{thought}|{seq}".encode("utf-8")).hexdigest()
            seen = self._ledger.get("reflection_seen")
            if not isinstance(seen, dict):
                seen = self._ledger["reflection_seen"] = {}
            if digest in seen:
                return None  # 24h anti-echo dedup: replays drop quietly
            seen[digest] = datetime.now(timezone.utc).isoformat()
            self._reflections.append(
                {"entity_id": f"reflection:{seq}", "thought": thought,
                 "about": [], "depth": depth, "seq": seq,
                 "ts": datetime.now(timezone.utc).isoformat()})
            return f"mapped self_reflection seq={seq}"

        def attach_memory_beliefs(self, entity_id, beliefs):
            for b in beliefs or []:
                rec = dict(b)
                rec["entity_id"] = entity_id
                self._memory_beliefs.append(rec)

        def note_sense_transitions(self, transitions):
            self._transitions = list(transitions or [])

        def attach_senses(self, readings):
            self._senses = [
                {"metric": r.metric, "status": r.status,
                 "prev_status": getattr(r, "prev_status", None)}
                for r in readings or []]

        def attach_environment(self, entity_id, fact):
            self._env.setdefault(entity_id, []).append(fact)

        def summary(self):
            return {"world_id": self.world.world_id,
                    "reality": "manifest",
                    "entities": len(self._entities),
                    "anchors": self._anchors,
                    "beliefs": self._beliefs,
                    "memory_beliefs": self._memory_beliefs,
                    "reflections": self._reflections,
                    "senses": self._senses,
                    "sense_transitions": self._transitions}

    vb.VerdandiBridge = VerdandiBridge

    _BULLET_TAG_RE = re.compile(r"^\[(\w+)\|(\w+)\]\s*(.*)$", re.S)
    _SALIENCE_RANK = {"high": 0, "medium": 1, "low": 2}

    def _read_bullets(path):
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            return []
        return [ln.strip()[2:].strip() for ln in text.splitlines()
                if ln.strip().startswith("- ")]

    def _belief_record(entity_id, claim, kind, salience, src):
        slug = "-".join(re.findall(r"[a-z0-9]+", claim.lower())[:4])
        return {"entity_id": entity_id,
                "subject": f"{entity_id}:{slug or 'claim'}",
                "claim": claim, "salience": salience,
                "confidence": 0.9, "kind": kind, "src": src,
                "supersedes": None,
                "formed_at": datetime.now(timezone.utc).isoformat()}

    def _parse_claims(path, src_label, claims, dead):
        for bullet in _read_bullets(path):
            if bullet.lower().startswith("supersedes:"):
                target = bullet[len("supersedes:"):].strip()
                dead.add(target)
                claims[:] = [c for c in claims if c[0] != target]
                continue
            m = _BULLET_TAG_RE.match(bullet)
            if m:
                kind, salience, claim = (m.group(1), m.group(2),
                                        m.group(3).strip())
            else:
                kind, salience, claim = "fact", "medium", bullet
            if not claim or claim in dead:
                continue
            if any(c[0] == claim for c in claims):
                continue
            claims.append((claim, kind, salience, src_label))

    def parse_memory_beliefs(home=None, now=None):
        home = home or os.path.expanduser("~")
        out = {}
        volmarr_claims: list = []
        dead: set = set()
        _parse_claims(os.path.join(home, "MEMORY.md"), "MEMORY.md",
                      volmarr_claims, dead)
        bank = os.path.join(home, "memory", "bank")
        try:
            bank_files = sorted(os.listdir(bank))
        except OSError:
            bank_files = []
        for name in bank_files:
            if name.endswith(".md"):
                _parse_claims(os.path.join(bank, name),
                              f"memory/bank/{name}", volmarr_claims, dead)
        now_dt = now or datetime.now(timezone.utc)
        mem_dir = os.path.join(home, "memory")
        try:
            mem_files = sorted(os.listdir(mem_dir))
        except OSError:
            mem_files = []
        for name in mem_files:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", name):
                continue
            try:
                day = datetime.strptime(name[:-3], "%Y-%m-%d").replace(
                    tzinfo=timezone.utc)
            except ValueError:
                continue
            if (now_dt - day).days <= 7:
                _parse_claims(os.path.join(mem_dir, name),
                              f"memory/{name}", volmarr_claims, dead)
        volmarr_claims.sort(key=lambda c: (_SALIENCE_RANK.get(c[2], 1),))
        out[vb.VOLMARR_ID] = [
            _belief_record(vb.VOLMARR_ID, claim, kind, salience, src)
            for claim, kind, salience, src in volmarr_claims[:40]]
        for slug in vb.PERSON_ROSTER:
            eid = f"person:{slug}"
            claims: list = []
            _parse_claims(os.path.join(home, "memory", "people", f"{slug}.md"),
                          f"memory/people/{slug}.md", claims, set())
            claims.sort(key=lambda c: (_SALIENCE_RANK.get(c[2], 1),))
            out[eid] = [_belief_record(eid, claim, kind, salience, src)
                        for claim, kind, salience, src in claims[:8]]
        return out

    vb.parse_memory_beliefs = parse_memory_beliefs

    def sample_senses(home=None, state_dir=None,
                      meminfo_path="/proc/meminfo", feed_path=None, now=None):
        status = "unknown"
        try:
            with open(meminfo_path, encoding="utf-8") as fh:
                text = fh.read()
            m = re.search(r"MemAvailable:\s+(\d+)", text)
            if m:
                mib = int(m.group(1)) / 1024
                status = ("ok" if mib >= 1024
                          else "warn" if mib >= 512 else "red")
        except OSError:
            pass
        return [SimpleNamespace(metric="mem_available_mib", status=status,
                                prev_status=None)]

    vb.sample_senses = sample_senses

    def environment_facts(now=None):
        iso = (now or datetime.now(timezone.utc)).isoformat()
        return [{"fact": "daily rhythm holds", "source": "clock", "at": iso},
                {"fact": "test double environment", "source": "fixture",
                 "at": iso}]

    vb.environment_facts = environment_facts

    bridges = types.ModuleType("wyrdforge.bridges")
    bridges.verdandi_bridge = vb
    pkg = types.ModuleType("wyrdforge")
    pkg.__path__ = []
    pkg.bridges = bridges
    return {"wyrdforge": pkg,
            "wyrdforge.bridges": bridges,
            "wyrdforge.bridges.verdandi_bridge": vb}


@pytest.fixture
def fake_wyrdforge():
    """Inject the wyrdforge test double into sys.modules (removed
    afterwards, so the real absence is visible again)."""
    names = ("wyrdforge", "wyrdforge.bridges",
             "wyrdforge.bridges.verdandi_bridge")
    saved = {k: sys.modules.get(k) for k in names}
    sys.modules.update(_build_fake_wyrdforge())
    try:
        yield sys.modules["wyrdforge.bridges.verdandi_bridge"]
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

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
def test_ledger_exactly_two_maps(paths, fake_wyrdforge):
    _write_feed(paths["feed_path"], [("ping", {})])
    run(emit=lambda t, d: None, **paths)
    ledger = _ledger(paths["ledger_path"])
    assert set(ledger.keys()) == {"last_sense_status", "reflection_seen"}


def test_corrupt_ledger_self_heals(paths, fake_wyrdforge):
    with open(paths["ledger_path"], "w", encoding="utf-8") as fh:
        fh.write("{not json")
    _write_feed(paths["feed_path"], [("ping", {})])
    result = run(emit=lambda t, d: None, **paths)
    assert result["changed"] is False
    ledger = _ledger(paths["ledger_path"])
    assert set(ledger.keys()) == {"last_sense_status", "reflection_seen"}
    assert ledger["last_sense_status"]["mem_available_mib"] == "ok"


def test_missing_ledger_is_fine(paths, fake_wyrdforge):
    assert not os.path.exists(paths["ledger_path"])
    _write_feed(paths["feed_path"], [("ping", {})])
    run(emit=lambda t, d: None, **paths)
    assert os.path.exists(paths["ledger_path"])


# -- the mirror is written every run; the witness only on mapped changes -------
def test_mirror_written_every_run(paths, fake_wyrdforge):
    _write_feed(paths["feed_path"], [("ping", {})])  # unmapped: quiet
    emitted = []
    result = run(emit=lambda t, d: emitted.append((t, d)), **paths)
    assert result["changed"] is False
    assert emitted == []
    mirror = _mirror(paths["mirror_path"])
    assert mirror["world_id"] == "heimr-wyrd-unnr"
    assert mirror["senses"]  # attach phase ran despite the quiet feed
    assert "memory_beliefs" in mirror and "reflections" in mirror


def test_witness_only_on_mapped(paths, fake_wyrdforge):
    _write_feed(paths["feed_path"], [
        ("mood_shift", {"after": {"valence": 0.8, "energy": 0.7}}),
    ])
    emitted = []
    result = run(emit=lambda t, d: emitted.append((t, d)), **paths)
    assert result["changed"] is True
    assert [t for t, _ in emitted] == ["wyrd_mirror_synced"]


def test_sense_transition_rewrites_mirror_without_witness(paths, fake_wyrdforge):
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
def test_excluded_events_remain_unmapped(fake_wyrdforge):
    from wyrdforge.bridges.verdandi_bridge import VerdandiBridge
    b = VerdandiBridge()
    for etype in ("ping", "entity.heartbeat", "wyrd_mirror_synced",
                  "wyrd_divergence", "wyrd_divergence_resolved",
                  "probe_recorded"):
        assert b.apply_event(etype, {}, TS) is None, etype


def test_no_sense_nerve_events(fake_wyrdforge):
    from wyrdforge.bridges.verdandi_bridge import VerdandiBridge
    handlers = VerdandiBridge()._handlers()
    assert not [k for k in handlers if k.startswith("sense_")]


def test_no_subprocesses_spawned(paths, fake_wyrdforge, monkeypatch):
    import subprocess

    def _boom(*a, **k):
        raise AssertionError("subprocess spawned during run()")

    monkeypatch.setattr(subprocess, "Popen", _boom)
    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr("os.system", _boom)
    _write_feed(paths["feed_path"], [("ping", {})])
    run(emit=lambda t, d: None, **paths)  # raises if anything shells out


# -- stable entities, roster, caps, supersedes ------------------------------------
def test_stable_ids_across_runs(paths, fake_wyrdforge):
    _write_feed(paths["feed_path"], [("ping", {})])
    run(emit=lambda t, d: None, **paths)
    ids1 = {e["entity_id"] for e in _mirror(paths["mirror_path"])["memory_beliefs"]}
    run(emit=lambda t, d: None, **paths)
    ids2 = {e["entity_id"] for e in _mirror(paths["mirror_path"])["memory_beliefs"]}
    assert ids1 == ids2 and ids1  # identity by stable key, not by rebuild


def test_inner_circle_entities(paths, fake_wyrdforge):
    _write_feed(paths["feed_path"], [("ping", {})])
    run(emit=lambda t, d: None, **paths)
    ids = {b["entity_id"]
           for b in _mirror(paths["mirror_path"])["memory_beliefs"]}
    assert {"person:veyrunn", "person:aurora",
            "person:caducea", "person:runa"} <= ids


def test_person_cap_eight(paths, fake_wyrdforge):
    page = os.path.join(paths["home"], "memory", "people", "veyrunn.md")
    with open(page, "w", encoding="utf-8") as fh:
        fh.write("---\nsummary: x.\n---\n## Facts\n" +
                 "".join(f"- fact {i}\n" for i in range(20)))
    _write_feed(paths["feed_path"], [("ping", {})])
    run(emit=lambda t, d: None, **paths)
    vey = [b for b in _mirror(paths["mirror_path"])["memory_beliefs"]
           if b["entity_id"] == "person:veyrunn"]
    assert len(vey) == 8


def test_volmarr_cap_forty(paths, fake_wyrdforge):
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


def test_supersedes_chain_in_mirror(paths, fake_wyrdforge):
    _write_feed(paths["feed_path"], [("ping", {})])
    run(emit=lambda t, d: None, **paths)
    claims = [b["claim"]
              for b in _mirror(paths["mirror_path"])["memory_beliefs"]]
    assert not any(c == "Volmarr's winter base is Truth or Consequences, "
                         "NM. (src: memory/2026-09-24.md:45)"
                   for c in claims)
    assert any("Nov-Mar" in c for c in claims)


# -- reflection round-trip ---------------------------------------------------------
def test_reflection_roundtrip_dedup(paths, fake_wyrdforge):
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


def test_depth2_reflection_refused_in_run(paths, fake_wyrdforge):
    _write_feed(paths["feed_path"], [
        ("self_reflection", {"thought": "meta meta", "seq": 2, "depth": 2}),
    ])
    result = run(emit=lambda t, d: None, **paths)
    assert result["changed"] is False
    assert _mirror(paths["mirror_path"])["reflections"] == []


# -- the run stays fast --------------------------------------------------------------
def test_run_inside_120s(paths, fake_wyrdforge):
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


# -- real backend integration (skips while the WYRD repo is absent) ----------
@requires_wyrdforge
def test_real_wyrdforge_bridge_surface():
    """The real wyrdforge backend exposes the bridge surface the Wave B
    attach phase relies on. Skipped with 'WYRD repo absent' until the
    sibling checkout exists."""
    from wyrdforge.bridges import verdandi_bridge as vb
    assert hasattr(vb, "VerdandiBridge")
    for name in ("VOLMARR_ID", "PERSON_ROSTER", "MACHINE_ID", "RHYTHM_ID",
                 "PLACE_ANGOLA_ID", "PLACE_TORC_ID", "parse_memory_beliefs",
                 "sample_senses", "environment_facts"):
        assert hasattr(vb, name), name
