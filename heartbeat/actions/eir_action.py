"""
Eir — The Healing Hand. Auto-Heal Action.

Eir is the goddess of healing. This action automatically repairs
corrupted databases, rebuilds indexes, and restores malformed
configuration files.

Configurable:
  - Which databases to repair
  - Whether to rebuild indexes
  - Whether to reset stuck services
  - Repair attempts before escalation
"""

import sqlite3
import shutil
import logging
from pathlib import Path
from typing import Any, Optional

from heartbeat.actions.base import (
    BaseAction, ActionContext, ActionResult, ActionSeverity, register_action,
)
from heartbeat.checks.base import CheckSeverity

logger = logging.getLogger("verdandi.heartbeat.actions.eir_action")


def _quote_ident(name: str) -> str:
    """Quote an SQLite identifier so arbitrary table names are safe in SQL."""
    return '"' + name.replace('"', '""') + '"'


@register_action("auto_heal")
class EirAction(BaseAction):
    """Auto-heal corrupted databases and fix configuration issues.

    Triggered by Mímir's memory check when databases fail integrity
    checks or have malformed data.
    """

    name = "auto_heal"
    description = "Auto-heal corrupted databases, rebuild indexes, restore configs"
    trigger_checks = ["memory"]
    trigger_severity = CheckSeverity.CRITICAL
    cooldown_seconds = 1800  # Don't heal the same issue more than once per 30 min

    def _execute(self, ctx: ActionContext) -> ActionResult:
        """Heal corrupted databases and fix broken state."""
        details = ctx.trigger_details
        targets_affected = []
        targets_failed = []

        # 1. Heal Mímir database if integrity failed
        mimir = details.get("mimir", {})
        if mimir.get("integrity") == "fail":
            success = self._heal_database(Path(mimir.get("path", "")), "mimir_well")
            if success:
                targets_affected.append("mimir_well:healed")
            else:
                targets_failed.append("mimir_well:heal_failed")

        # 2. Heal state database if integrity failed
        state_db = details.get("state_db", {})
        if state_db.get("integrity") == "fail":
            success = self._heal_database(Path(state_db.get("path", "")), "verdandi_heartbeat")
            if success:
                targets_affected.append("state_db:healed")
            else:
                targets_failed.append("state_db:heal_failed")

        # 3. Ensure nerve hub socket directory exists
        from heartbeat.paths import get_state_dir, ensure_dirs
        try:
            ensure_dirs()
            targets_affected.append("directories:ensured")
        except Exception as e:
            logger.error(f"Failed to ensure directories: {e}")
            targets_failed.append("directories:ensure_failed")

        # 4. Truncate conversation log if it has malformed entries
        conv_log = details.get("conversation_log", {})
        if conv_log.get("exists"):
            success = self._heal_jsonl(
                Path(conv_log.get("path", ""))
            )
            if success:
                targets_affected.append("conversation_log:healed")
            # Non-critical if this fails

        # 5. Truncate nerve feed if it has malformed entries
        nerve_feed = details.get("nerve_feed", {})
        if nerve_feed.get("exists"):
            success = self._heal_jsonl(
                Path(nerve_feed.get("path", ""))
            )
            if success:
                targets_affected.append("nerve_feed:healed")

        if targets_failed:
            severity = ActionSeverity.PARTIAL if targets_affected else ActionSeverity.FAILED
        elif targets_affected:
            severity = ActionSeverity.SUCCESS
        else:
            severity = ActionSeverity.SKIPPED

        return ActionResult(
            action_name=self.name,
            severity=severity,
            message=f"Healed {len(targets_affected)} targets, {len(targets_failed)} failed",
            details={"affected": targets_affected, "failed": targets_failed},
            targets_affected=targets_affected,
            targets_failed=targets_failed,
        )

    def _dry_run(self, ctx: ActionContext) -> ActionResult:
        """Report what would be healed."""
        details = ctx.trigger_details
        would_heal = []

        mimir = details.get("mimir", {})
        if mimir.get("integrity") == "fail":
            would_heal.append("mimir_well DB")

        state_db = details.get("state_db", {})
        if state_db.get("integrity") == "fail":
            would_heal.append("state_db")

        return ActionResult(
            action_name=self.name,
            severity=ActionSeverity.DRY_RUN,
            message=f"[DRY-RUN] Would heal {len(would_heal)} targets: {', '.join(would_heal)}",
            details={"targets": would_heal},
        )

    def _heal_database(self, db_path: Path, name: str) -> bool:
        """Attempt to repair a corrupted SQLite database.

        The kept oath: never destroy what we cannot restore.

        Strategy:
          1. Copy the suspect file to a recovery backup (``<name>.db.recover``).
             The backup is NOT deleted until the rebuilt database verifies.
          2. Fast path: if ``PRAGMA integrity_check`` reports "ok", the DB was
             never corrupt — VACUUM it, discard the backup, return True.
          3. Otherwise move the corrupted file aside (``<name>.db.corrupt``)
             for forensics and rebuild a fresh DB by ATTACHing the backup and
             copying every table's schema and rows across.
          4. Verify the rebuild: ``integrity_check`` must be "ok" and every
             restored table must hold exactly as many rows as the backup.
          5. Only on success is the backup consumed. On ANY failure the backup
             is kept, the failure is logged loudly, and False is returned —
             never a True on an empty database.
        """
        backup_path = db_path.with_suffix(".db.recover")
        corrupted_path = db_path.with_suffix(".db.corrupt")

        if not db_path.exists():
            logger.warning(f"Database {name} not found at {db_path}")
            return False

        # Step 1: take a recovery backup that we refuse to lose.
        try:
            shutil.copy2(str(db_path), str(backup_path))
        except OSError as e:
            logger.error(
                "Eir auto-heal FAILURE [%s]: cannot create recovery backup of %s: %s. "
                "Refusing to touch the database.",
                name, db_path, e,
            )
            return False

        # Step 2: fast path — the DB may not be corrupt at all.
        try:
            with sqlite3.connect(str(db_path)) as conn:
                if conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok":
                    conn.execute("VACUUM")
                    backup_path.unlink(missing_ok=True)
                    logger.info("Database %s verified healthy; vacuumed.", name)
                    return True
        except sqlite3.DatabaseError as e:
            logger.warning(
                "Eir auto-heal [%s]: integrity check failed (%s); "
                "attempting restore from recovery backup.",
                name, e,
            )

        # Step 3: restore — move the corrupt file aside, rebuild from backup.
        try:
            if corrupted_path.exists():
                # Forensics copy already kept from an earlier run.
                db_path.unlink(missing_ok=True)
            else:
                shutil.move(str(db_path), str(corrupted_path))

            table_defs = self._backup_table_defs(backup_path)
            self._restore_tables(backup_path, db_path, table_defs)
            self._verify_restore(db_path, table_defs)
        except Exception as e:
            logger.error(
                "Eir auto-heal FAILURE [%s]: restore from recovery backup failed: %s. "
                "Corrupted original preserved at %s; backup preserved at %s. "
                "Manual intervention required.",
                name, e, corrupted_path, backup_path,
            )
            # Do not leave the database missing: put the corrupted original
            # back in place so nothing is silently destroyed.
            if not db_path.exists() and corrupted_path.exists():
                try:
                    shutil.copy2(str(corrupted_path), str(db_path))
                except OSError as ce:
                    logger.error(
                        "Eir auto-heal FAILURE [%s]: could not put the corrupted "
                        "original back at %s: %s",
                        name, db_path, ce,
                    )
            return False

        # Step 4: verification passed — only now may the backup be consumed.
        backup_path.unlink(missing_ok=True)
        logger.info(
            "Eir auto-heal SUCCESS [%s]: rebuilt %s and restored %d table(s); "
            "integrity ok, row counts match the backup.",
            name, db_path, len(table_defs),
        )
        return True

    @staticmethod
    def _backup_table_defs(backup_path: Path) -> list:
        """Read ``(name, DDL, row count)`` for every user table in the backup.

        Raises if the backup itself cannot be read — a backup we cannot read
        is a restore we must not attempt.
        """
        defs = []
        with sqlite3.connect(str(backup_path)) as conn:
            rows = conn.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            for table_name, ddl in rows:
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {_quote_ident(table_name)}"
                ).fetchone()[0]
                defs.append((table_name, ddl, count))
        return defs

    @staticmethod
    def _restore_tables(backup_path: Path, db_path: Path, table_defs: list) -> None:
        """Rebuild ``db_path`` by ATTACHing the backup and copying schema+rows."""
        with sqlite3.connect(str(db_path)) as new_conn:
            new_conn.execute("ATTACH DATABASE ? AS heal_backup", (str(backup_path),))
            try:
                for table_name, ddl, _count in table_defs:
                    quoted = _quote_ident(table_name)
                    if ddl:
                        new_conn.execute(ddl)
                    else:
                        # Schema text unreadable — fall back to a structure copy.
                        new_conn.execute(
                            f"CREATE TABLE {quoted} AS "
                            f"SELECT * FROM heal_backup.{quoted} WHERE 0"
                        )
                    new_conn.execute(
                        f"INSERT INTO {quoted} SELECT * FROM heal_backup.{quoted}"
                    )
                # Rebuild indexes declared in the backup (auto-indexes come
                # back on their own with the table constraints).
                for (index_sql,) in new_conn.execute(
                    "SELECT sql FROM heal_backup.sqlite_master "
                    "WHERE type = 'index' AND sql IS NOT NULL"
                ):
                    new_conn.execute(index_sql)
                # Preserve AUTOINCREMENT sequence values if the backup has them.
                has_seq = new_conn.execute(
                    "SELECT name FROM heal_backup.sqlite_master "
                    "WHERE name = 'sqlite_sequence'"
                ).fetchone()
                if has_seq:
                    new_conn.execute(
                        "INSERT INTO sqlite_sequence "
                        "SELECT * FROM heal_backup.sqlite_sequence"
                    )
                new_conn.commit()
            finally:
                try:
                    new_conn.execute("DETACH DATABASE heal_backup")
                except sqlite3.Error as de:
                    logger.debug("DETACH of heal_backup raised (harmless): %s", de)

    @staticmethod
    def _verify_restore(db_path: Path, table_defs: list) -> None:
        """Raise unless the rebuilt DB is clean and row counts match the backup."""
        with sqlite3.connect(str(db_path)) as conn:
            check = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if check != "ok":
                raise RuntimeError(f"rebuilt database failed integrity_check: {check!r}")
            for table_name, _ddl, expected in table_defs:
                got = conn.execute(
                    f"SELECT COUNT(*) FROM {_quote_ident(table_name)}"
                ).fetchone()[0]
                if got != expected:
                    raise RuntimeError(
                        f"row count mismatch on {table_name!r}: "
                        f"backup has {expected}, rebuilt has {got}"
                    )

    def _heal_jsonl(self, path: Path) -> bool:
        """Remove malformed lines from a JSONL file."""
        import json

        if not path.exists():
            return True

        try:
            valid_lines = []
            removed = 0

            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        json.loads(line)
                        valid_lines.append(line + "\n")
                    except json.JSONDecodeError:
                        removed += 1

            if removed > 0:
                with open(path, "w") as f:
                    f.writelines(valid_lines)
                logger.info(f"Healed {path.name}: removed {removed} malformed lines")

            return True

        except Exception as e:
            logger.error(f"Failed to heal {path.name}: {e}")
            return False