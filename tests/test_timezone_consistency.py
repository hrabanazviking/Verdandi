"""Timezone consistency audit for Verðandi.

Slice 13 (2026-10-10 forge run): all timestamps emitted by the runtime must be
tz-aware ISO 8601 produced via ``datetime.now(timezone.utc).isoformat()``.
``datetime.utcnow()`` is banned from non-test source because it returns a naive
datetime that downstream code may mistake for UTC (or for local time).

These tests are real assertions over the real tree — not static snapshots.
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_ROOT = Path(__file__).resolve().parent.parent
# Built via concatenation so this test file's own source never contains the
# literal banned pattern as a plain call.
_BANNED_CALL = re.compile(r"\bdatetime" + r"\.utcnow" + r"\s*\(")

_EXCLUDED_PARTS = {"tests", "__pycache__", ".git", ".venv", "venv", "node_modules"}


def _iter_source_files(root: Path):
    for path in root.rglob("*.py"):
        parts = path.relative_to(root).parts
        if any(p in _EXCLUDED_PARTS or p.startswith(".") for p in parts):
            continue
        yield path


def test_no_datetime_utcnow_in_non_test_source():
    """Fail the suite if any non-test .py file calls datetime.utcnow()."""
    offenders = []
    for path in _iter_source_files(REPO_ROOT):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if _BANNED_CALL.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "naive datetime.utcnow() calls found in non-test source "
        "(use datetime.now(timezone.utc) instead): "
        + ", ".join(sorted(offenders))
    )


def test_utcnow_helper_emits_tz_aware_iso8601():
    """muse_aspects._utcnow() returns a tz-aware ISO 8601 string."""
    from muse_aspects import _utcnow

    ts = _utcnow()
    parsed = datetime.fromisoformat(ts)
    assert parsed.utcoffset() is not None, f"naive timestamp emitted: {ts!r}"


def test_autobiography_shares_tz_aware_utcnow():
    """autobiography.py emits the same tz-aware helper (its as_of/ts fields)."""
    import autobiography
    import muse_aspects

    assert autobiography._utcnow is muse_aspects._utcnow
    parsed = datetime.fromisoformat(autobiography._utcnow())
    assert parsed.utcoffset() is not None


def test_emitted_snapshot_and_record_fields_are_tz_aware(tmp_path):
    """Real emitted fields — mood snapshot as_of, reward/shadow ts — parse tz-aware."""
    from muse_aspects import GefanRewards, HugrMood, SkuggiShadow

    mood = HugrMood(state_dir=tmp_path)
    snap = mood.snapshot()
    assert datetime.fromisoformat(snap["as_of"]).utcoffset() is not None

    rewards = GefanRewards(state_dir=tmp_path, mood=HugrMood(state_dir=tmp_path))
    entry = rewards.record("tests_green", note="slice-13 audit")
    assert datetime.fromisoformat(entry["ts"]).utcoffset() is not None

    shadow = SkuggiShadow(state_dir=tmp_path, mood=HugrMood(state_dir=tmp_path))
    sig = shadow.record("sloppy_work", note="slice-13 audit")
    assert datetime.fromisoformat(sig["ts"]).utcoffset() is not None
