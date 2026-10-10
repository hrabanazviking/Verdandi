"""Tests for wyrd_bridge.py (Roadmap Worlds, Slice 1, Verðandi half).

The runner projects the nerve feed into the WYRD mirror world, stays
silent when nothing is new, and witnesses real syncs on the nerve.
"""
import json
import os
import sys
import time

import pytest

# The runner imports wyrdforge from the WYRD repo — same as production.
WYRD_SRC = os.path.join(os.path.expanduser("~"), "workspace", "repos",
                        "WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model",
                        "src")
if WYRD_SRC not in sys.path:
    sys.path.insert(0, WYRD_SRC)

import wyrd_bridge
from wyrd_bridge import run


def _wyrdforge_importable():
    try:
        import wyrdforge  # noqa: F401
        return True
    except ImportError:
        return False


_WYRD_AVAILABLE = _wyrdforge_importable()

# Tests that need the REAL wyrdforge backend skip while the WYRD repo is
# absent. Tests below that exercise wyrd_bridge's decoupled logic use the
# fake_wyrdforge fixture instead and run regardless.
requires_wyrdforge = pytest.mark.skipif(not _WYRD_AVAILABLE,
                                        reason="WYRD repo absent")


def _build_fake_wyrdforge():
    """Build a minimal wyrdforge test double.

    Implements exactly the surface wyrd_bridge.py uses: the VerdandiBridge
    class (apply_event/summary/ensure_entity/attach_memory_beliefs/
    note_sense_transitions/attach_senses/attach_environment), the vb
    constants (VOLMARR_ID, PERSON_ROSTER, MACHINE_ID, RHYTHM_ID,
    PLACE_ANGOLA_ID, PLACE_TORC_ID) and the vb functions
    (parse_memory_beliefs/sample_senses/environment_facts).

    It is a TEST DOUBLE, not the real backend: event mapping, memory
    parsing (with supersedes/death-of-claims and the 40/8 caps), sense
    sampling (mem_available_mib ok/warn/red) and the 24h reflection
    anti-echo dedup are reimplemented faithfully enough that
    wyrd_bridge's own decoupled logic — stable IDs, mapping, supersedes
    chains, transition detection, ledger shape, witness gating — is
    genuinely exercised. Anything genuinely backend-specific (the real
    bridge's full handler table, real sense suite) stays in the
    requires_wyrdforge-marked tests.
    """
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

    # Feed event types the bridge deliberately ignores (mirrors the real
    # backend's exclusion list: the nerve's own bookkeeping never maps).
    _UNMAPPED = {"ping", "entity.heartbeat", "wyrd_mirror_synced",
                 "wyrd_divergence", "wyrd_divergence_resolved",
                 "probe_recorded"}

    class _FakeWorld:
        def __init__(self):
            self.world_id = "heimr-wyrd-unnr"
            self.identity = SimpleNamespace(reality="manifest")

        def registry_entry(self):
            # Plain-dict handshake shape, as WorldRegistry.register accepts.
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

        # -- entities --------------------------------------------------
        def ensure_entity(self, entity_id, kinds):
            self._entities.setdefault(entity_id, set()).update(kinds)

        # -- feed mapping ----------------------------------------------
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

        # -- attach phase ----------------------------------------------
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

    # -- memory parsing (read-only) ----------------------------------------
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
        """Append (claim, kind, salience, src) for each live bullet.

        A "- supersedes: <claim>" bullet kills the claim text: it is
        removed from what is accumulated AND added to `dead`, so later
        identical bullets stay dead. Exact duplicate claims dedup.
        """
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
        # Daily logs: last 7 days only.
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
        volmarr_claims.sort(
            key=lambda c: (_SALIENCE_RANK.get(c[2], 1),))
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

    # -- senses --------------------------------------------------------------
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

    # -- environment -----------------------------------------------------------
    def environment_facts(now=None):
        iso = (now or datetime.now(timezone.utc)).isoformat()
        return [{"fact": "daily rhythm holds", "source": "clock", "at": iso},
                {"fact": "test double environment", "source": "fixture",
                 "at": iso}]

    vb.environment_facts = environment_facts

    bridges = types.ModuleType("wyrdforge.bridges")
    bridges.verdandi_bridge = vb
    pkg = types.ModuleType("wyrdforge")
    pkg.__path__ = []  # mark as a package so submodule imports resolve
    pkg.bridges = bridges
    return {"wyrdforge": pkg,
            "wyrdforge.bridges": bridges,
            "wyrdforge.bridges.verdandi_bridge": vb}


@pytest.fixture
def fake_wyrdforge():
    """Inject the wyrdforge test double into sys.modules.

    Lets wyrd_bridge's decoupled logic run while the real WYRD repo is
    absent. Everything is removed afterwards so the real absence is
    visible again to other tests.
    """
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


def _write_feed(path, entries):
    now = time.time()
    with open(path, "w", encoding="utf-8") as fh:
        for i, (etype, data) in enumerate(entries, start=1):
            fh.write(json.dumps({"type": etype, "data": data,
                                 "_seq": i, "_ts": now + i}) + "\n")


@pytest.fixture
def paths(tmp_path):
    # Scratch everything the Wave B attach phase can touch: the ledger,
    # the memory home, and the hermes state dir. Tests never reach live
    # state — no memory reads, no ledger writes outside tmp_path.
    state_dir = tmp_path / "state"
    home_dir = tmp_path / "home"
    state_dir.mkdir()
    home_dir.mkdir()
    return {
        "feed_path": str(tmp_path / "nerve_feed.jsonl"),
        "cursor_path": str(tmp_path / "cursor.json"),
        "mirror_path": str(tmp_path / "wyrd_mirror.json"),
        "registry_path": str(tmp_path / "registry.json"),
        "ledger_path": str(state_dir / "wyrd_entity_ledger.json"),
        "home": str(home_dir),
        "state_dir": str(state_dir),
    }


def test_sync_maps_mood_and_wish(paths, fake_wyrdforge):
    _write_feed(paths["feed_path"], [
        ("ping", {}),
        ("mood_shift", {"after": {"valence": 0.8, "energy": 0.7},
                        "why": "shipped slice 1"}),
        ("wish_made", {"wish_id": "w1", "text": "Learn Old Norse",
                       "why": "mine"}),
    ])
    emitted = []
    result = run(emit=lambda t, d: emitted.append((t, d)), **paths)
    assert result["changed"] is True
    summary = result["summary"]
    assert summary["world_id"] == "heimr-wyrd-unnr"
    assert summary["reality"] == "manifest"
    assert len(summary["anchors"]) == 2
    assert len(summary["beliefs"]) == 2  # mood belief + wish belief
    assert len(emitted) == 1
    assert emitted[0][0] == "wyrd_mirror_synced"
    assert emitted[0][1]["new_events"] == 2
    # durable projection written
    with open(paths["mirror_path"], encoding="utf-8") as fh:
        mirror = json.load(fh)
    assert mirror["world_id"] == "heimr-wyrd-unnr"


def test_registry_flips_to_manifest_active(paths, fake_wyrdforge):
    _write_feed(paths["feed_path"], [
        ("wish_made", {"wish_id": "w1", "text": "t"}),
    ])
    run(emit=lambda t, d: None, **paths)
    import worlds
    reg = worlds.WorldRegistry(path=paths["registry_path"])
    entry = reg.get("heimr-wyrd-unnr")
    assert entry.reality == "manifest"
    assert entry.status == "active"


def test_silent_when_nothing_new(paths, fake_wyrdforge):
    _write_feed(paths["feed_path"], [
        ("wish_made", {"wish_id": "w1", "text": "t"}),
    ])
    emitted = []
    first = run(emit=lambda t, d: emitted.append((t, d)), **paths)
    assert first["changed"] is True
    emitted.clear()
    second = run(emit=lambda t, d: emitted.append((t, d)), **paths)
    assert second["changed"] is False
    assert emitted == []


def test_unmapped_events_advance_cursor_but_stay_silent(paths, fake_wyrdforge):
    _write_feed(paths["feed_path"], [("ping", {}), ("ping", {})])
    emitted = []
    result = run(emit=lambda t, d: emitted.append((t, d)), **paths)
    assert result["changed"] is False
    assert emitted == []
    with open(paths["cursor_path"], encoding="utf-8") as fh:
        assert json.load(fh)["last_seq"] == 2


def test_missing_feed_is_quiet(paths, fake_wyrdforge):
    emitted = []
    result = run(emit=lambda t, d: emitted.append((t, d)), **paths)
    assert result["changed"] is False
    assert emitted == []


# -- Slice 3: typed unavailability -------------------------------------------
@pytest.mark.skipif(_WYRD_AVAILABLE, reason="WYRD repo present")
def test_load_wyrdforge_raises_typed_error():
    """Slice 3: an absent WYRD repo raises WyrdUnavailableError (an
    ImportError), never a bare ModuleNotFoundError — and the message
    names the expected repo path."""
    assert issubclass(wyrd_bridge.WyrdUnavailableError, ImportError)
    with pytest.raises(wyrd_bridge.WyrdUnavailableError) as ei:
        wyrd_bridge._load_wyrdforge()
    assert wyrd_bridge.WYRD_REPO in str(ei.value)


@pytest.mark.skipif(_WYRD_AVAILABLE, reason="WYRD repo present")
def test_load_wyrdforge_repo_present_but_broken(tmp_path, monkeypatch):
    """Slice 3: the repo dir exists but the import still fails -> the
    same typed error, naming the repo path."""
    repo = tmp_path / "wyrdrepo"
    (repo / "src").mkdir(parents=True)
    monkeypatch.setattr(wyrd_bridge, "WYRD_REPO", str(repo))
    with pytest.raises(wyrd_bridge.WyrdUnavailableError) as ei:
        wyrd_bridge._load_wyrdforge()
    assert str(repo) in str(ei.value)


@pytest.mark.skipif(_WYRD_AVAILABLE, reason="WYRD repo present")
def test_run_raises_typed_error_without_backend(tmp_path):
    """Slice 3: run() surfaces WyrdUnavailableError when the backend is
    absent (main() still catches it and exits 1 — the nerve never
    breaks)."""
    with pytest.raises(wyrd_bridge.WyrdUnavailableError):
        run(feed_path=str(tmp_path / "feed.jsonl"),
            emit=lambda t, d: None)


# -- real backend integration (skips while the WYRD repo is absent) ----------
@requires_wyrdforge
def test_real_wyrdforge_backend_surface():
    """The real wyrdforge bridge exposes the surface wyrd_bridge relies
    on. Skipped with 'WYRD repo absent' until the sibling checkout
    exists."""
    from wyrdforge.bridges import verdandi_bridge as vb
    assert hasattr(vb, "VerdandiBridge")
    for name in ("VOLMARR_ID", "PERSON_ROSTER", "MACHINE_ID", "RHYTHM_ID",
                 "PLACE_ANGOLA_ID", "PLACE_TORC_ID", "parse_memory_beliefs",
                 "sample_senses", "environment_facts"):
        assert hasattr(vb, name), name
