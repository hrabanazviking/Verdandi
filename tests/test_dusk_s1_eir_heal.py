"""
Dusk run "The Kept Oath" — Slice S1.

Regression tests for the Eir ``_heal_database`` data-loss bug: the old restore
path ran ``CREATE TABLE ... AS SELECT * FROM backup.<table>`` without ever
ATTACHing the backup, so the SELECT raised (swallowed by ``except: pass``), the
fresh DB was committed EMPTY, the backup was deleted, and the heal returned
True. These tests pin the fixed behavior with real sqlite databases:

  - a corrupted DB whose rows are still readable is rebuilt with every row,
    integrity "ok", and the backup consumed only after verification;
  - an unreadable corruption makes heal return False (loudly) and keeps the
    backup file;
  - a missing/uncreatable backup makes heal return False without touching
    the original.
"""

import logging
import os
import sqlite3
from pathlib import Path

from heartbeat.actions.eir_action import EirAction


def _make_db(path: Path, rows: int = 500) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, body TEXT)")
    conn.executemany(
        "INSERT INTO events (body) VALUES (?)", [(f"row-{i}",) for i in range(rows)]
    )
    conn.execute("CREATE INDEX idx_body ON events(body)")
    conn.execute("CREATE TABLE kv (k TEXT PRIMARY KEY, v TEXT)")
    conn.executemany(
        "INSERT INTO kv VALUES (?, ?)", [(f"k{i}", f"v{i}") for i in range(50)]
    )
    conn.commit()
    conn.close()


def _corrupt_index_rootpage(path: Path) -> None:
    """Corrupt the DB so integrity_check fails but every row stays readable.

    Repoints an index at another table's b-tree rootpage: the schema still
    parses and full table scans work, but integrity_check raises
    "database disk image is malformed".
    """
    conn = sqlite3.connect(str(path))
    kv_root = conn.execute(
        "SELECT rootpage FROM sqlite_master WHERE name='kv'"
    ).fetchone()[0]
    conn.execute("PRAGMA writable_schema=ON")
    conn.execute(
        "UPDATE sqlite_master SET rootpage=? WHERE type='index' AND name='idx_body'",
        (kv_root,),
    )
    conn.execute("PRAGMA writable_schema=OFF")
    conn.commit()
    conn.close()


def _smash_data_pages(path: Path) -> None:
    """Destroy data pages with random bytes: unreadable even for table scans."""
    size = path.stat().st_size
    with open(path, "r+b") as f:
        f.seek(size // 3)
        f.write(os.urandom(size // 3))


def _integrity_first(path: Path):
    """Return ('rows', [...]) or ('raised', msg) for PRAGMA integrity_check."""
    conn = sqlite3.connect(str(path))
    try:
        try:
            return ("rows", [r[0] for r in conn.execute("PRAGMA integrity_check").fetchall()])
        except sqlite3.DatabaseError as e:
            return ("raised", str(e))
    finally:
        conn.close()


def test_heal_restores_all_rows_from_corrupt_db(tmp_path):
    db_path = tmp_path / "mimir.db"
    _make_db(db_path)
    _corrupt_index_rootpage(db_path)

    kind, detail = _integrity_first(db_path)
    assert kind == "raised" and "malformed" in detail  # genuinely detected as corrupt

    action = EirAction()
    assert action._heal_database(db_path, "mimir_well") is True

    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 500
        assert conn.execute("SELECT COUNT(*) FROM kv").fetchone()[0] == 50
        # spot-check content, not just counts
        assert conn.execute(
            "SELECT body FROM events WHERE id = 499"
        ).fetchone()[0] == "row-498"
        assert conn.execute("SELECT v FROM kv WHERE k = 'k7'").fetchone()[0] == "v7"
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert tables == {"events", "kv"}
    finally:
        conn.close()

    # The old bug left tables == [] and deleted the backup; the fixed path
    # consumes the backup only after verification passed.
    assert not (tmp_path / "mimir.db.recover").exists()


def test_heal_returns_false_and_keeps_backup_on_unreadable_db(tmp_path, caplog):
    db_path = tmp_path / "mimir.db"
    _make_db(db_path)
    _smash_data_pages(db_path)

    action = EirAction()
    with caplog.at_level(logging.ERROR, logger="verdandi.heartbeat.actions.eir_action"):
        assert action._heal_database(db_path, "mimir_well") is False

    # The failure is logged loudly, not swallowed.
    assert any("FAILURE" in r.message for r in caplog.records)

    # The backup — the one surviving copy of the data — is preserved.
    backup_path = tmp_path / "mimir.db.recover"
    assert backup_path.exists()

    # The corrupted original was put back in place; the DB is not left missing.
    assert db_path.exists()


def test_heal_returns_false_when_backup_cannot_be_created(tmp_path, caplog):
    db_path = tmp_path / "state.db"
    _make_db(db_path)
    # Block backup creation: symlink the backup path into a missing directory
    # so shutil.copy2 raises instead of silently copying elsewhere.
    (tmp_path / "state.db.recover").symlink_to(tmp_path / "no-such-dir" / "x.db")

    action = EirAction()
    with caplog.at_level(logging.ERROR, logger="verdandi.heartbeat.actions.eir_action"):
        assert action._heal_database(db_path, "verdandi_heartbeat") is False

    assert any("FAILURE" in r.message for r in caplog.records)

    # Original untouched — all rows still there.
    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 500
    finally:
        conn.close()


def test_heal_healthy_db_still_vacuums_and_returns_true(tmp_path):
    db_path = tmp_path / "healthy.db"
    _make_db(db_path)

    action = EirAction()
    assert action._heal_database(db_path, "mimir_well") is True

    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 500
    finally:
        conn.close()
    assert not (tmp_path / "healthy.db.recover").exists()


def test_heal_missing_db_returns_false(tmp_path, caplog):
    action = EirAction()
    with caplog.at_level(logging.WARNING, logger="verdandi.heartbeat.actions.eir_action"):
        assert action._heal_database(tmp_path / "gone.db", "mimir_well") is False
