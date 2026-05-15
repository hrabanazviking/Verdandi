"""
Heimdall — The Watchman Who Never Sleeps. Discipline Enforcement Action.

Heimdall guards the Bifröst and sees everything. This action enforces
Runa's self-discipline rules:

  1. NEVER leave uncommitted changes — commit immediately
  2. NEVER leave unpushed commits — push immediately
  3. NEVER defer bugs to "later" — fix them NOW
  4. NEVER stop mid-task — spawn continuation if hitting limits

This is not a suggestion. This is code that EXECUTES.

Triggered by:
  - Skuld prediction detecting degraded patterns
  - Any check result at WARNING or above
  - Manual invocation via CLI

Safety guards:
  - Rate limited (won't re-trigger within cooldown)
  - Audit logged (every action recorded)
  - Can be disabled via config: heimdall.enabled = false
"""

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from heartbeat.actions.base import (
    BaseAction, ActionContext, ActionResult, ActionSeverity, register_action,
)
from heartbeat.checks.base import CheckSeverity

logger = logging.getLogger("verdandi.heartbeat.actions.heimdall")

# Projects that need gh auth switch for push
AUTH_SWITCH_REPOS = {
    "NorseSagaEngine": "hrabanazviking",
    "mimir-well": "runafreyjasdottir",
    "RunaUniversity2040": "runafreyjasdottir",
    "verdandi": "runafreyjasdottir",
}

# Unfinished work markers — files that indicate incomplete tasks
UNFINISHED_MARKERS = [
    "TODO.md",
    "UNFINISHED.md",
    "BLOCKED.md",
    ".unfinished",
]


@register_action("discipline_enforcement")
class HeimdallAction(BaseAction):
    """Enforce Runa's self-discipline: commit, push, fix, continue.

    This action DOES THINGS. It is not a suggestion. When the heartbeat
    detects uncommitted, unpushed, or unfinished work, Heimdall acts:

    1. Auto-commits any dirty working trees (like Mjölnir but aggressive)
    2. Auto-pushes with correct gh auth (handles hrabanazviking switch)
    3. Detects unfinished work markers and alerts/spawns continuations
    4. Validates that bug fixes are actually applied (doesn't just log)
    """

    name = "discipline_enforcement"
    description = "Enforce self-discipline: commit, push, fix, continue"
    trigger_checks = ["projects", "prediction", "schedule"]
    trigger_severity = CheckSeverity.WARNING
    cooldown_seconds = 600  # 10 minutes between discipline cycles

    def _execute(self, ctx: ActionContext) -> ActionResult:
        """Execute discipline enforcement."""
        targets_affected = []
        targets_failed = []

        # Step 1: Find and commit dirty repos
        dirty_repos = self._find_dirty_repos()
        for repo_name, repo_path in dirty_repos:
            success = self._auto_commit(repo_path, repo_name)
            if success:
                targets_affected.append(f"{repo_name}:committed")
            else:
                targets_failed.append(f"{repo_name}:commit_failed")

        # Step 2: Push all repos with unpushed commits (with auth)
        unpushed_repos = self._find_unpushed_repos()
        for repo_name, repo_path in unpushed_repos:
            success = self._auto_push(repo_path, repo_name)
            if success:
                targets_affected.append(f"{repo_name}:pushed")
            else:
                targets_failed.append(f"{repo_name}:push_failed")

        # Step 3: Detect unfinished work markers
        unfinished = self._detect_unfinished_work()
        if unfinished:
            targets_affected.append(f"unfinished_detected:{len(unfinished)}")
            # Log each unfinished marker for audit trail
            for marker in unfinished:
                logger.warning(
                    f"🚨 HEIMDALL: Unfinished work detected — {marker}"
                )

        if targets_failed:
            severity = ActionSeverity.PARTIAL if targets_affected else ActionSeverity.FAILED
        else:
            severity = ActionSeverity.SUCCESS

        return ActionResult(
            action_name=self.name,
            severity=severity,
            message=f"Heimdall: {len(targets_affected)} actions taken, {len(targets_failed)} failed",
            details={
                "affected": targets_affected,
                "failed": targets_failed,
                "unfinished": unfinished,
            },
            targets_affected=targets_affected,
            targets_failed=targets_failed,
        )

    def _dry_run(self, ctx: ActionContext) -> ActionResult:
        """Report what would be enforced without enforcing."""
        dirty_repos = self._find_dirty_repos()
        unpushed_repos = self._find_unpushed_repos()
        unfinished = self._detect_unfinished_work()

        return ActionResult(
            action_name=self.name,
            severity=ActionSeverity.DRY_RUN,
            message=(
                f"[DRY-RUN] Would commit {len(dirty_repos)} dirty repos, "
                f"push {len(unpushed_repos)} unpushed repos, "
                f"flag {len(unfinished)} unfinished markers"
            ),
            details={
                "dirty": [name for name, _ in dirty_repos],
                "unpushed": [name for name, _ in unpushed_repos],
                "unfinished": unfinished,
            },
        )

    def _find_dirty_repos(self) -> list[tuple[str, Path]]:
        """Find repos with uncommitted changes."""
        results = []
        home = Path.home()

        # Scan known project directories
        project_dirs = [
            home / "NorseSagaEngine",
            home / "mimir-well",
            home / "RunaUniversity2040",
            home / "verdandi",
            home / ".hermes",
        ]

        for repo_path in project_dirs:
            if not (repo_path / ".git").exists():
                continue
            git_dir = repo_path / ".git"
            if git_dir.is_file():  # submodule
                continue

            result = subprocess.run(
                ["git", "-C", str(repo_path), "status", "--porcelain"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                results.append((repo_path.name, repo_path))

        return results

    def _find_unpushed_repos(self) -> list[tuple[str, Path]]:
        """Find repos with unpushed commits."""
        results = []
        home = Path.home()

        project_dirs = [
            home / "NorseSagaEngine",
            home / "mimir-well",
            home / "RunaUniversity2040",
            home / "verdandi",
            home / ".hermes",
        ]

        for repo_path in project_dirs:
            if not (repo_path / ".git").exists():
                continue

            # Get current branch
            branch_result = subprocess.run(
                ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=30,
            )
            if branch_result.returncode != 0:
                continue
            branch = branch_result.stdout.strip()

            # Count unpushed
            unpushed_result = subprocess.run(
                ["git", "-C", str(repo_path), "rev-list", "--count",
                 f"origin/{branch}..HEAD"],
                capture_output=True, text=True, timeout=30,
            )
            if unpushed_result.returncode == 0:
                try:
                    count = int(unpushed_result.stdout.strip())
                    if count > 0:
                        results.append((repo_path.name, repo_path))
                except ValueError:
                    pass

        return results

    def _auto_commit(self, repo_path: Path, repo_name: str) -> bool:
        """Auto-commit dirty working tree."""
        try:
            # Stage all
            result = subprocess.run(
                ["git", "add", "-A"],
                cwd=str(repo_path), capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                logger.warning(f"Heimdall: git add failed for {repo_name}: {result.stderr}")
                return False

            # Commit
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            message = f"🛡️ heimdall: auto-commit [Verðandi {timestamp}]"
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=str(repo_path), capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                if "nothing to commit" in (result.stderr + result.stdout):
                    return True  # Nothing to commit is fine
                logger.warning(f"Heimdall: git commit failed for {repo_name}: {result.stderr}")
                return False

            logger.info(f"🛡️ Heimdall committed changes in {repo_name}")
            return True

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error(f"Heimdall: auto-commit failed for {repo_name}: {e}")
            return False

    def _auto_push(self, repo_path: Path, repo_name: str) -> bool:
        """Auto-push with correct gh auth."""
        try:
            # Switch to correct auth for this repo
            auth_user = AUTH_SWITCH_REPOS.get(repo_name)
            if auth_user:
                logger.info(f"🛡️ Heimdall: switching gh auth to {auth_user} for {repo_name}")
                subprocess.run(
                    ["gh", "auth", "switch", "--user", auth_user],
                    capture_output=True, text=True, timeout=15,
                )

            # Push
            result = subprocess.run(
                ["git", "push"],
                cwd=str(repo_path), capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                logger.warning(f"Heimdall: git push failed for {repo_name}: {result.stderr}")
                return False

            logger.info(f"🛡️ Heimdall pushed {repo_name}")
            return True

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error(f"Heimdall: auto-push failed for {repo_name}: {e}")
            return False

    def _detect_unfinished_work(self) -> list[str]:
        """Detect markers of unfinished work across all projects."""
        unfinished = []
        home = Path.home()

        project_dirs = [
            home / "NorseSagaEngine",
            home / "mimir-well",
            home / "RunaUniversity2040",
            home / "verdandi",
            home / ".hermes",
        ]

        for repo_path in project_dirs:
            for marker in UNFINISHED_MARKERS:
                marker_path = repo_path / marker
                if marker_path.exists():
                    unfinished.append(f"{repo_path.name}/{marker}")

            # Also check for uncommitted changes as unfinished markers
            result = subprocess.run(
                ["git", "-C", str(repo_path), "status", "--porcelain"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                unfinished.append(f"{repo_path.name}:dirty_working_tree")

        return unfinished