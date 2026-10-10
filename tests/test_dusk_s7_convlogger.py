"""
Dusk S7 (S9+S10) tests for conversation_logger.py — memory integrity.

S9: current.json writes are atomic (tmp + fsync + os.replace); corrupt or
    truncated current.json is LOUD (stderr warning + backup to
    current.json.corrupt.<ts>) instead of silently discarded.
S10: type-shape crashes fixed — valid-JSON-wrong-type current.json (e.g. `[]`)
     no longer crashes cmd_event; non-string content no longer crashes cmd_show.
"""

import argparse
import glob
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_DIR = Path(__file__).parent.parent
import sys
sys.path.insert(0, str(PROJECT_DIR))

import conversation_logger as cl


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def isolate_paths(tmp_path):
    """Redirect all paths to a temp dir to avoid touching production."""
    state_dir = tmp_path / ".hermes" / "state"
    conv_dir = state_dir / "conversations"
    state_dir.mkdir(parents=True, exist_ok=True)
    conv_dir.mkdir(parents=True, exist_ok=True)

    original_constants = {
        'STATE_DIR': cl.STATE_DIR,
        'CONV_DIR': cl.CONV_DIR,
        'CURRENT_FILE': cl.CURRENT_FILE,
        'CONV_LOG': cl.CONV_LOG,
    }
    cl.STATE_DIR = state_dir
    cl.CONV_DIR = conv_dir
    cl.CURRENT_FILE = state_dir / "current.json"
    cl.CONV_LOG = state_dir / "conversation_log.jsonl"

    yield {
        'state_dir': state_dir,
        'conv_dir': conv_dir,
        'current_file': cl.CURRENT_FILE,
        'conv_log': cl.CONV_LOG,
    }

    for key, val in original_constants.items():
        setattr(cl, key, val)


def make_ns(command, **kwargs):
    return argparse.Namespace(command=command, **kwargs)


def corrupt_backups(state_dir):
    return glob.glob(str(state_dir / "current.json.corrupt.*"))


def start_session(session="dusk-s7", summary="dusk test"):
    cl.cmd_start(make_ns('start', session=session, summary=summary,
                         model='pytest', platform='pytest'))


# ============================================================================
# S9 — atomic writes
# ============================================================================

class TestAtomicWrites:
    def test_write_is_atomic_mid_write_failure_keeps_old_state(self, isolate_paths):
        """Simulate kill-mid-write: if the replace never lands, old state survives."""
        v1 = {"session_id": "s", "decisions": ["use postgres"], "files_changed": ["a.py"]}
        cl._write_json_atomic(cl.CURRENT_FILE, v1)

        v2 = {"session_id": "s", "decisions": ["use redis"], "files_changed": []}
        with patch("conversation_logger.os.replace", side_effect=OSError("kill -9 mid-write")):
            with pytest.raises(OSError):
                cl._write_json_atomic(cl.CURRENT_FILE, v2)

        # Old state fully intact — never a torn file
        with open(cl.CURRENT_FILE) as f:
            assert json.load(f) == v1

    def test_all_commands_leave_valid_current_json(self, isolate_paths):
        """start/event/update/end each produce parseable current.json."""
        start_session()
        cl.cmd_event(make_ns('event', session='dusk-s7', type='decision',
                             content='use postgres'))
        cl.cmd_update(make_ns('update', session='dusk-s7', next=['ship it'],
                              blockers=None, projects=[], mood='focused',
                              summary=''))
        cl.cmd_end(make_ns('end', session='dusk-s7', summary='done', duration=5))
        with open(cl.CURRENT_FILE) as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert data["decisions"] == ["use postgres"]
        assert data["status"] == "closed"

    def test_no_stray_tmp_files_left_behind(self, isolate_paths):
        """Atomic writes must not litter the state dir with tmp files."""
        start_session()
        cl.cmd_event(make_ns('event', session='dusk-s7', type='decision',
                             content='x'))
        stray = glob.glob(str(isolate_paths['state_dir'] / ".current.json.tmp.*"))
        assert stray == []


# ============================================================================
# S9 — loud corrupt handling (kill-mid-write simulation)
# ============================================================================

class TestLoudCorruptHandling:
    def test_truncated_current_json_warns_and_backs_up(self, isolate_paths, capsys):
        """Kill-mid-write simulation: torn file -> loud warning + backup, no silent loss."""
        start_session()
        cl.cmd_event(make_ns('event', session='dusk-s7', type='decision',
                             content='use postgres'))
        # Simulate a torn write: valid JSON prefix, abruptly cut off
        torn = '{"session_id": "dusk-s7", "decisions": ["use post'
        cl.CURRENT_FILE.write_text(torn)

        state = cl.get_current_state()

        err = capsys.readouterr().err
        assert "CORRUPT/TRUNCATED" in err
        assert "backed up" in err
        backups = corrupt_backups(isolate_paths['state_dir'])
        assert len(backups) == 1
        assert Path(backups[0]).read_text() == torn  # evidence preserved
        assert state == {}  # fresh start, honestly empty
        assert not cl.CURRENT_FILE.exists()  # torn file moved aside, no repeat warnings

    def test_cmd_event_survives_truncated_current_json(self, isolate_paths, capsys):
        """The exact S9 repro shape: event after a torn write must not crash."""
        start_session()
        cl.cmd_event(make_ns('event', session='dusk-s7', type='decision',
                             content='use postgres'))
        cl.CURRENT_FILE.write_text('{"decisions": ["use post')  # torn

        cl.cmd_event(make_ns('event', session='dusk-s7', type='decision',
                             content='use redis'))

        err = capsys.readouterr().err
        assert "CORRUPT/TRUNCATED" in err
        with open(cl.CURRENT_FILE) as f:
            data = json.load(f)  # must be valid JSON again
        assert data["decisions"] == ["use redis"]

    def test_cmd_update_and_end_survive_truncated_file(self, isolate_paths):
        start_session()
        cl.CURRENT_FILE.write_text('{"status": "act')  # torn
        cl.cmd_update(make_ns('update', session='dusk-s7', next=['a'],
                              blockers=None, projects=[], mood='', summary=''))
        cl.cmd_end(make_ns('end', session='dusk-s7', summary='done', duration=1))
        with open(cl.CURRENT_FILE) as f:
            assert json.load(f)["status"] == "closed"

    def test_empty_file_is_corrupt_loud(self, isolate_paths, capsys):
        start_session()
        cl.CURRENT_FILE.write_text('')  # zero-byte file from a crashed write
        assert cl.get_current_state() == {}
        assert "CORRUPT/TRUNCATED" in capsys.readouterr().err
        assert len(corrupt_backups(isolate_paths['state_dir'])) == 1


# ============================================================================
# S10 — type-shape crashes
# ============================================================================

class TestTypeShapeCrashes:
    def test_list_current_json_no_crash_loud_backup(self, isolate_paths, capsys):
        """S10(a): `[]` in current.json must not crash cmd_event."""
        start_session()
        cl.CURRENT_FILE.write_text('[]')  # valid JSON, wrong type

        # Used to die: AttributeError: 'list' object has no attribute 'setdefault'
        cl.cmd_event(make_ns('event', session='dusk-s7', type='decision',
                             content='use redis'))

        err = capsys.readouterr().err
        assert "WRONG TYPE" in err
        backups = corrupt_backups(isolate_paths['state_dir'])
        assert len(backups) == 1
        assert json.loads(Path(backups[0]).read_text()) == []
        with open(cl.CURRENT_FILE) as f:
            data = json.load(f)
        assert data["decisions"] == ["use redis"]  # fresh start, event recorded

    def test_string_current_json_no_crash(self, isolate_paths, capsys):
        start_session()
        cl.CURRENT_FILE.write_text('"just a string"')
        assert cl.get_current_state() == {}
        assert "WRONG TYPE" in capsys.readouterr().err

    def test_int_content_cmd_show_no_crash(self, isolate_paths, capsys):
        """S10(b): non-string content must not crash cmd_show."""
        start_session()
        # Hand-craft entries with non-string shapes, as real-world logs may hold
        with open(cl.CONV_LOG, "a") as f:
            f.write(json.dumps({"entry_type": "event", "timestamp": "2026-10-10T00:00:00",
                                "session_id": "dusk-s7", "event_type": "decision",
                                "content": 42}) + "\n")
            f.write(json.dumps({"entry_type": "start", "timestamp": "2026-10-10T00:00:00",
                                "session_id": "dusk-s7", "summary": 12345}) + "\n")
            f.write(json.dumps({"entry_type": "update", "timestamp": "2026-10-10T00:00:00",
                                "session_id": "dusk-s7", "next_actions": "notalist"}) + "\n")

        cl.cmd_show(make_ns('show', session='dusk-s7'))  # must not raise

        out = capsys.readouterr().out
        assert "42" in out
        assert "12345" in out

    def test_cmd_recent_survives_nonstring_summary(self, isolate_paths, capsys):
        start_session(session="dusk-r", summary="ok")
        with open(cl.CONV_LOG, "a") as f:
            f.write(json.dumps({"entry_type": "end", "timestamp": "2026-10-10T00:00:00",
                                "session_id": "dusk-r", "summary": {"weird": True}}) + "\n")
        cl.cmd_recent(make_ns('recent', count=5))  # must not raise
        assert "dusk-r" in capsys.readouterr().out

    def test_context_survives_nonstring_fields(self, isolate_paths):
        """get_context_for_cron must not crash on odd but valid dict shapes."""
        cl.CURRENT_FILE.write_text(json.dumps({
            "session_id": "dusk-s7", "status": "active",
            "decisions": [1, 2, 3], "next_actions": [None],
            "summary": 999, "blockers": ["b1"],
        }))
        ctx = cl.get_context_for_cron(max_sessions=1)  # must not raise
        assert "dusk-s7" in ctx

    def test_event_with_wrong_typed_list_fields_recovers(self, isolate_paths):
        """A dict-shaped file with non-list list-fields must not crash cmd_event."""
        start_session()
        cl.CURRENT_FILE.write_text(json.dumps({"session_id": "dusk-s7",
                                               "decisions": "use postgres"}))
        cl.cmd_event(make_ns('event', session='dusk-s7', type='decision',
                             content='use redis'))
        with open(cl.CURRENT_FILE) as f:
            assert json.load(f)["decisions"] == ["use redis"]

    def test_blocker_resolved_with_wrong_typed_blockers(self, isolate_paths):
        start_session()
        cl.CURRENT_FILE.write_text(json.dumps({"session_id": "dusk-s7",
                                               "blockers": 42}))
        cl.cmd_event(make_ns('event', session='dusk-s7',
                             type='blocker_resolved', content='b1'))
        with open(cl.CURRENT_FILE) as f:
            assert json.load(f)["blockers"] == []
