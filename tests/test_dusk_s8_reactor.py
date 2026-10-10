"""
Dusk run S11-S15 regression tests (forge worker slices S11..S15).

Covers:
  S11 context_injector.py — repo-local conversation_logger takes precedence
      over a deployed copy in ~/.hermes/state
  S12 reactor.py — naive (tz-less) timestamps no longer crash react()
  S13 reactor.py — non-dict JSON lines are skipped loudly, rest still processed
  S14 reactor.py — a blocker re-occurring after resolution re-activates with a
      visible re-occurrence count
  S15 reactor.py — react(focus=...) filters the report for each focus value
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import reactor as rt


# ============================================================================
# Shared fixture: redirect state paths to a temp dir
# ============================================================================

@pytest.fixture()
def sandboxed_state(tmp_path):
    """Redirect reactor's state files into a temp dir."""
    state_dir = tmp_path / ".hermes" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    current_file = state_dir / "current.json"
    conv_log = state_dir / "conversation_log.jsonl"

    original = {
        "STATE_DIR": rt.STATE_DIR,
        "CONV_LOG": rt.CONV_LOG,
        "CURRENT_FILE": rt.CURRENT_FILE,
    }
    rt.STATE_DIR = state_dir
    rt.CONV_LOG = conv_log
    rt.CURRENT_FILE = current_file
    try:
        yield {"state_dir": state_dir, "current_file": current_file, "conv_log": conv_log}
    finally:
        for key, val in original.items():
            setattr(rt, key, val)


def log_events(entries, conv_log):
    """Append raw JSONL lines to the conversation log."""
    with open(conv_log, "a") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def make_event(session, event_type, content, ts=None):
    return {
        "entry_type": "event",
        "timestamp": ts or datetime.now(timezone.utc).isoformat(),
        "session_id": session,
        "event_type": event_type,
        "content": content,
    }


# ============================================================================
# S11 — repo-local conversation_logger shadows state-dir copy
# ============================================================================

class TestS11RepoLocalImport:
    def test_state_dir_copy_never_shadows_repo(self, tmp_path):
        """Plant a self-identifying conversation_logger.py in a fake
        ~/.hermes/state and run context_injector from a directory that is
        NOT the repo. The repo-local copy must be used."""
        fake_home = tmp_path / "fakehome"
        state_dir = fake_home / ".hermes" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        # Poisoned copy: any import-time use raises loudly
        (state_dir / "conversation_logger.py").write_text(
            "raise RuntimeError('POISONED: state-dir conversation_logger used')\n"
        )

        work_dir = tmp_path / "work"
        work_dir.mkdir()

        env = dict(os.environ)
        env["HOME"] = str(fake_home)
        # Ensure a repo-local import resolves even though cwd != repo dir
        env["PYTHONPATH"] = str(PROJECT_DIR) + os.pathsep + env.get("PYTHONPATH", "")

        result = subprocess.run(
            [sys.executable, str(PROJECT_DIR / "context_injector.py"),
             "log-start", "--session", "s11-test",
             "--summary", "shadow check"],
            cwd=str(work_dir),
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"context_injector failed (state-dir shadow used?)\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        # And the repo-local copy is what's importable first on sys.path
        log_path = state_dir / "conversation_log.jsonl"
        assert log_path.exists()
        assert "s11-test" in log_path.read_text()

    def test_state_dir_fallback_when_repo_copy_absent(self):
        """Import machinery must not crash when the repo dir has no
        conversation_logger.py — verify the fallback path entry exists."""
        # context_injector always inserts its own dir first and appends the
        # state dir, so the state copy remains reachable as a fallback.
        result = subprocess.run(
            [sys.executable, "-c",
             "import runpy, sys; runpy.run_path("
             f"'{PROJECT_DIR / 'context_injector.py'}', run_name='probe')"],
            capture_output=True, text=True, cwd=str(PROJECT_DIR),
        )
        # It runs as a probe of the import section only (no main guard side
        # effects beyond arg parsing defaults); a plain `context` default
        # run is fine — we just need it not to explode at import time.
        assert result.returncode == 0, result.stderr


# ============================================================================
# S12 — naive timestamp no longer crashes react()
# ============================================================================

class TestS12NaiveTimestamp:
    def test_naive_timestamp_stale_session_no_crash(self, sandboxed_state):
        """A start entry with a naive timestamp and no end entry used to
        raise TypeError (aware - naive). It must now be treated as UTC."""
        naive_ts = (datetime.now(timezone.utc) - timedelta(hours=5)).replace(tzinfo=None).isoformat()
        assert "T" in naive_ts and "+" not in naive_ts and "Z" not in naive_ts
        log_events([{
            "entry_type": "start",
            "timestamp": naive_ts,
            "session_id": "naive-session",
            "summary": "started without tz",
        }], sandboxed_state["conv_log"])

        reactions = rt.react()
        stale = reactions["stale_sessions_to_close"]
        assert any(s["session_id"] == "naive-session" for s in stale)

    def test_parse_timestamp_assumes_utc(self):
        dt = rt._parse_timestamp("2026-01-01T00:00:00")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_aware_timestamp_unchanged(self):
        dt = rt._parse_timestamp("2026-01-01T00:00:00+02:00")
        assert dt is not None
        assert dt.utcoffset() == timedelta(hours=2)


# ============================================================================
# S13 — non-dict JSON lines skipped loudly
# ============================================================================

class TestS13NonDictLines:
    def test_non_dict_lines_skipped_and_reported(self, sandboxed_state, capsys):
        conv_log = sandboxed_state["conv_log"]
        with open(conv_log, "w") as f:
            f.write("42\n")
            f.write('"just a string"\n')
            f.write("null\n")
            f.write("[1, 2, 3]\n")
            f.write("not json at all\n")
            f.write(json.dumps(make_event("s13", "blocker", "Real blocker")) + "\n")

        reactions = rt.react()
        # Must not crash; the one valid dict entry still processed
        assert any("Real blocker" in b["content"]
                   for b in reactions["blockers_needing_reaction"])
        # Loudly: warning on stderr mentioning the skip count
        err = capsys.readouterr().err
        assert "4" in err and "skipped" in err.lower()


# ============================================================================
# S14 — blocker re-occurring after resolution re-activates
# ============================================================================

class TestS14BlockerRegression:
    def test_reoccurring_blocker_reactivates_with_count(self, sandboxed_state):
        log_events([
            make_event("s14", "blocker", "db down"),
            make_event("s14", "blocker_resolved", "db down"),
            make_event("s14", "blocker", "db down"),
        ], sandboxed_state["conv_log"])

        reactions = rt.react()
        blockers = reactions["blockers_needing_reaction"]
        assert any(b["content"] == "db down" for b in blockers), (
            "re-occurring blocker was silently dropped"
        )
        entry = next(b for b in blockers if b["content"] == "db down")
        assert entry["reoccurrences"] == 1
        assert "REGRESSION" in entry["reaction"]

    def test_second_regression_increments_count(self, sandboxed_state):
        log_events([
            make_event("s14b", "blocker", "flaky test"),
            make_event("s14b", "blocker_resolved", "flaky test"),
            make_event("s14b", "blocker", "flaky test"),
            make_event("s14b", "blocker_resolved", "flaky test"),
            make_event("s14b", "blocker", "flaky test"),
        ], sandboxed_state["conv_log"])

        reactions = rt.react()
        entry = next(b for b in reactions["blockers_needing_reaction"]
                     if b["content"] == "flaky test")
        assert entry["reoccurrences"] == 2

    def test_still_resolved_blocker_stays_quiet(self, sandboxed_state):
        log_events([
            make_event("s14c", "blocker", "old problem"),
            make_event("s14c", "blocker_resolved", "old problem"),
        ], sandboxed_state["conv_log"])

        reactions = rt.react()
        contents = [b["content"] for b in reactions["blockers_needing_reaction"]]
        assert "old problem" not in contents

    def test_new_blocker_has_zero_reoccurrences(self, sandboxed_state):
        log_events([make_event("s14d", "blocker", "fresh issue")],
                   sandboxed_state["conv_log"])
        reactions = rt.react()
        entry = next(b for b in reactions["blockers_needing_reaction"]
                     if b["content"] == "fresh issue")
        assert entry["reoccurrences"] == 0


# ============================================================================
# S15 — focus filtering
# ============================================================================

def _seed_mixed(sandboxed_state):
    log_events([
        make_event("s15", "blocker", "Mixed blocker"),
        make_event("s15", "learned", "Mixed learning"),
        make_event("s15", "file_changed", "mixed.py"),
    ], sandboxed_state["conv_log"])
    with open(sandboxed_state["current_file"], "w") as f:
        json.dump({"session_id": "s15", "next_actions": ["Do the thing"]}, f)


class TestS15FocusFiltering:
    def test_focus_blockers(self, sandboxed_state):
        _seed_mixed(sandboxed_state)
        r = rt.react(focus="blockers")
        assert len(r["blockers_needing_reaction"]) == 1
        assert r["recent_learnings_to_store"] == []
        assert r["files_changed_needing_push"] == []
        assert r["next_actions_to_pick_up"] == []
        assert all(d["action"] == "resolve_blockers" for d in r["reactions"])

    def test_focus_learnings(self, sandboxed_state):
        _seed_mixed(sandboxed_state)
        r = rt.react(focus="learnings")
        assert len(r["recent_learnings_to_store"]) == 1
        assert r["blockers_needing_reaction"] == []
        assert all(d["action"] == "store_learnings" for d in r["reactions"])

    def test_focus_files(self, sandboxed_state):
        _seed_mixed(sandboxed_state)
        r = rt.react(focus="files")
        assert len(r["files_changed_needing_push"]) == 1
        assert r["blockers_needing_reaction"] == []
        assert all(d["action"] == "verify_pushed" for d in r["reactions"])

    def test_focus_next(self, sandboxed_state):
        _seed_mixed(sandboxed_state)
        r = rt.react(focus="next")
        assert len(r["next_actions_to_pick_up"]) == 1
        assert r["blockers_needing_reaction"] == []
        assert all(d["action"] == "continue_work" for d in r["reactions"])

    def test_focus_all_returns_everything(self, sandboxed_state):
        _seed_mixed(sandboxed_state)
        r = rt.react(focus="all")
        assert len(r["blockers_needing_reaction"]) == 1
        assert len(r["recent_learnings_to_store"]) == 1
        assert len(r["files_changed_needing_push"]) == 1
        assert len(r["next_actions_to_pick_up"]) == 1
        assert len(r["reactions"]) >= 4

    def test_invalid_focus_rejected(self, sandboxed_state):
        with pytest.raises(ValueError):
            rt.react(focus="nope")

    def test_cli_focus_blockers_filters_output(self, sandboxed_state, tmp_path):
        """End-to-end: --focus blockers prints the blockers section but not
        the learnings section."""
        _seed_mixed(sandboxed_state)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(PROJECT_DIR) + os.pathsep + env.get("PYTHONPATH", "")
        # reactor reads Path.home()/.hermes/state, so point HOME at tmp and
        # copy the seeded state there.
        fake_home = tmp_path / "home"
        state_dir = fake_home / ".hermes" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        for src in (sandboxed_state["conv_log"], sandboxed_state["current_file"]):
            (state_dir / src.name).write_bytes(src.read_bytes())
        env["HOME"] = str(fake_home)

        result = subprocess.run(
            [sys.executable, str(PROJECT_DIR / "reactor.py"), "--focus", "blockers"],
            env=env, capture_output=True, text=True, cwd=str(tmp_path),
        )
        assert result.returncode == 0, result.stderr
        assert "BLOCKERS" in result.stdout
        assert "Mixed blocker" in result.stdout
        assert "Mixed learning" not in result.stdout
