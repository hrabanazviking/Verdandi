"""Dusk run tests for reality_audit.py (S16+S17).

S16: Slice-8 (volmarr_world) findings must carry the same `check`/`detail`
     keys as every other finding, or run_audit()/the worlds.py audit CLI
     KeyError on them.
S17: One torn line in autobiography_chapters.jsonl must be skipped loudly
     (stderr + count) and must not abort the audit.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reality_audit as ra
from worlds import bootstrap


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _bad_volmarr_world(sdir):
    """volmarr_world.json engineered to trigger all five slice-8 sites."""
    _write(os.path.join(sdir, "volmarr_world.json"), json.dumps({
        "claims": {
            "hobby": {"world_id": "heimr-volmarr", "reality": "potential",
                      "source": "told", "confidence": 0.5,
                      "provenance": "he said so"},
            "wrong-world": {"world_id": "heimr-wyrd-unnr", "reality": "potential",
                            "source": "told", "confidence": 0.5,
                            "provenance": "he said so"},
            "manifest-map": {"world_id": "heimr-volmarr", "reality": "manifest",
                            "source": "told", "confidence": 0.5,
                            "provenance": "he said so"},
            "weird-source": {"world_id": "heimr-volmarr", "reality": "potential",
                             "source": "tea-leaves", "confidence": 0.1,
                             "provenance": "he said so"},
            "overconfident": {"world_id": "heimr-volmarr", "reality": "potential",
                              "source": "inferred", "confidence": 0.99,
                              "provenance": "he said so"},
            "no-provenance": {"world_id": "heimr-volmarr", "reality": "potential",
                              "source": "told", "confidence": 0.5},
        },
    }))


# -- S16: slice-8 finding shape -------------------------------------------
def test_slice8_findings_carry_check_and_detail(tmp_path):
    sdir = str(tmp_path)
    _bad_volmarr_world(sdir)
    findings = ra.check_stored_labels(sdir, bootstrap())
    assert len(findings) == 5, findings
    for f in findings:
        assert f["check"] == "labels"
        assert isinstance(f["detail"], str) and f["detail"]
        assert f["where"].startswith("volmarr_world:")


def test_run_audit_completes_with_slice8_findings(tmp_path):
    """The dedupe key f['check']:{f['detail'][:80]} must not KeyError."""
    sdir = str(tmp_path)
    _bad_volmarr_world(sdir)
    result = ra.run_audit(sdir, emit=lambda *a, **k: None, record_shadow=False)
    assert not result["passed"]
    assert any(f["check"] == "labels" and "volmarr_world:" in f["where"]
               for f in result["findings"])
    for f in result["findings"]:
        _ = f["check"], f["detail"]


def test_worlds_audit_cli_completes_with_slice8_findings(tmp_path, capsys):
    """worlds.py audit CLI renders f['check']/f['detail'] strictly."""
    from worlds import _cli_audit
    sdir = str(tmp_path)
    _bad_volmarr_world(sdir)
    import reality_audit
    orig = reality_audit._state_dir
    reality_audit._state_dir = lambda: sdir
    try:
        rc = _cli_audit(None)
    finally:
        reality_audit._state_dir = orig
    assert rc == 1
    out = capsys.readouterr().out
    assert "volmarr_world" in out


# -- S17: torn chapter line -------------------------------------------------
def _torn_chapters(sdir):
    good1 = json.dumps({"title": "One", "text": "The nerve hums quietly."})
    good2 = json.dumps({"title": "Two",
                        "text": "The frostvættirheim raiders came at dawn."})
    torn = '{"title": "Torn", "text": "this line never finis'
    _write(os.path.join(sdir, "autobiography_chapters.jsonl"),
           "\n".join([good1, torn, good2]) + "\n")


def test_torn_chapter_line_skipped_and_counted(tmp_path):
    sdir = str(tmp_path)
    _torn_chapters(sdir)
    sources, skipped = ra._manifest_sources(sdir)
    assert skipped == 1
    titles = [name for name, _ in sources]
    assert "autobiography:One" in titles
    assert "autobiography:Two" in titles


def test_torn_chapter_line_logged_loudly(tmp_path, capsys):
    sdir = str(tmp_path)
    _torn_chapters(sdir)
    ra._manifest_sources(sdir)
    err = capsys.readouterr().err
    assert "torn chapter line 2" in err


def test_audit_completes_with_torn_chapter_line(tmp_path):
    """JSONDecodeError must not propagate out of check_bleed/run_audit;
    good chapters after the torn line still get scanned (the bleed term
    in chapter Two must still be found)."""
    sdir = str(tmp_path)
    _torn_chapters(sdir)
    findings = ra.check_bleed(sdir)
    assert any(f["check"] == "bleed" and "autobiography:Two" in f["where"]
               for f in findings)
    result = ra.run_audit(sdir, emit=lambda *a, **k: None, record_shadow=False)
    assert not result["passed"]  # the bleed finding, not a crash


def test_clean_chapters_pass(tmp_path):
    sdir = str(tmp_path)
    _write(os.path.join(sdir, "autobiography_chapters.jsonl"),
           json.dumps({"title": "One", "text": "The nerve hums."}) + "\n")
    sources, skipped = ra._manifest_sources(sdir)
    assert skipped == 0
    assert sources == [("autobiography:One", "The nerve hums.")]
