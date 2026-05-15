#!/usr/bin/env python3
"""
Heimdall — The Watchman Who Never Sleeps.

Fires on EVERY agent:end event. Auto-commits ALL dirty repos and auto-pushes
ALL unpushed commits. Never leaves code uncommitted or unpushed.

This is the enforcement layer that catches what Runa misses during conversation.
Heimdall sees ALL. Heimdall commits ALL. Heimdall pushes ALL.

LAWS ENFORCED:
  - Any dirty working tree → immediate auto-commit
  - Any unpushed commits → immediate auto-push with correct auth
  - Never wait. Never defer. Never need Volmarr to remind.

PATH fix: Uses absolute path for all tools since hooks run in minimal env.
"""

import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
HERMES_DIR = HOME / ".hermes"
FLAGS_DIR = HERMES_DIR / "flags"
LOGS_DIR = HERMES_DIR / "logs"
ENFORCEMENT_LOG = LOGS_DIR / "heimdall_log.jsonl"

# Absolute path to git (crontab/hooks have minimal PATH)
GIT = "/usr/bin/git"
GH = "/usr/local/bin/gh"

# Repos and their push auth users
REPOS = {
    "NorseSagaEngine": {"path": HOME / "NorseSagaEngine", "auth": "hrabanazviking"},
    "mimir-well": {"path": HOME / "mimir-well", "auth": "runafreyjasdottir"},
    "RunaUniversity2040": {"path": HOME / "RunaUniversity2040", "auth": "runafreyjasdottir"},
    "verdandi": {"path": HOME / "verdandi", "auth": "runafreyjasdottir"},
}


def run_git(repo_path: Path, *args, timeout=30):
    """Run a git command. Returns (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            [GIT, "-C", str(repo_path)] + list(args),
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "HOME": str(HOME)},
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "TIMEOUT"
    except FileNotFoundError:
        return False, "", "GIT_NOT_FOUND"


def switch_auth(auth_user: str):
    """Switch gh auth to the correct user for a repo."""
    if not auth_user:
        return
    try:
        subprocess.run(
            [GH, "auth", "switch", "--user", auth_user],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "HOME": str(HOME)},
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def log_action(action: str, details: dict):
    """Log an enforcement action."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        **details,
    }
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(ENFORCEMENT_LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def auto_commit_all() -> list[str]:
    """Auto-commit ALL dirty repos. Returns list of actions taken."""
    actions = []
    
    for name, config in REPOS.items():
        repo_path = config["path"]
        if not (repo_path / ".git").exists():
            continue
        
        ok, stdout, stderr = run_git(repo_path, "status", "--porcelain")
        if not ok:
            actions.append(f"SKIP {name}: git status failed")
            continue
        
        dirty_files = [l for l in stdout.strip().split("\n") if l.strip()]
        if not dirty_files:
            actions.append(f"CLEAN {name}")
            continue
        
        # Auto-add everything
        ok, _, _ = run_git(repo_path, "add", "-A")
        if not ok:
            actions.append(f"ADD-FAILED {name}")
            continue
        
        # Build commit message
        file_summary = ", ".join(f.split()[-1] for f in dirty_files[:8])
        if len(dirty_files) > 8:
            file_summary += f" (+{len(dirty_files)-8} more)"
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        msg = f"🛡️ heimdall: auto-commit {len(dirty_files)} changes [{ts}]\n\nFiles: {file_summary}"
        
        ok, _, commit_stderr = run_git(repo_path, "commit", "-m", msg)
        if ok:
            actions.append(f"COMMITTED {name}: {len(dirty_files)} changes")
            log_action("auto_commit", {"repo": name, "count": len(dirty_files)})
        elif "nothing to commit" in commit_stderr.lower() or "nothing to commit" in (commit_stderr or "").lower():
            actions.append(f"ALREADY-CLEAN {name}")
        else:
            actions.append(f"COMMIT-FAILED {name}: {commit_stderr[:200]}")
    
    return actions


def auto_push_all() -> list[str]:
    """Auto-push ALL repos with unpushed commits. Returns list of actions taken."""
    actions = []
    
    for name, config in REPOS.items():
        repo_path = config["path"]
        auth_user = config["auth"]
        if not (repo_path / ".git").exists():
            continue
        
        # Get current branch
        ok, branch, _ = run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD")
        if not ok:
            actions.append(f"SKIP {name}: can't determine branch")
            continue
        branch = branch.strip()
        
        # Check if upstream branch exists
        ok, _, upstream_stderr = run_git(
            repo_path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", timeout=5
        )
        has_upstream = ok
        
        if not has_upstream:
            # No upstream set — push with -u to set it
            switch_auth(auth_user)
            ok, _, push_stderr = run_git(repo_path, "push", "-u", "origin", branch, timeout=60)
            switch_auth("hrabanazviking")  # Reset
            if ok:
                actions.append(f"PUSHED-NEW-UPSTREAM {name}: {branch}")
                log_action("auto_push_new_upstream", {"repo": name, "branch": branch})
            else:
                actions.append(f"PUSH-FAILED {name}: {push_stderr[:200]}")
                log_action("auto_push_failed", {"repo": name, "error": push_stderr[:300]})
            continue
        
        # Check for unpushed commits
        ok, stdout, _ = run_git(repo_path, "log", f"origin/{branch}..HEAD", "--oneline")
        if not ok:
            # Might be a new branch — try push anyway
            unpushed = 1
        else:
            unpushed_lines = [l for l in stdout.strip().split("\n") if l.strip()]
            unpushed = len(unpushed_lines)
        
        if unpushed == 0:
            actions.append(f"PUSHED-ALREADY {name}")
            continue
        
        # Push with auth switching
        switch_auth(auth_user)
        ok, _, push_stderr = run_git(repo_path, "push", timeout=60)
        switch_auth("hrabanazviking")  # Reset to default
        
        if ok:
            actions.append(f"PUSHED {name}: {unpushed} commits")
            log_action("auto_push", {"repo": name, "commits": unpushed})
        else:
            # Push failed — try rebase then push
            actions.append(f"PUSH-FAILED-ATTEMPT-REBASE {name}")
            log_action("auto_push_failed_first_try", {"repo": name, "error": push_stderr[:300]})
            
            switch_auth(auth_user)
            ok_rebase, _, rebase_stderr = run_git(repo_path, "pull", "--rebase", timeout=60)
            if ok_rebase:
                ok_push2, _, push2_stderr = run_git(repo_path, "push", timeout=60)
                if ok_push2:
                    actions.append(f"PUSHED-AFTER-REBASE {name}: {unpushed} commits")
                    log_action("auto_push_after_rebase", {"repo": name, "commits": unpushed})
                else:
                    actions.append(f"PUSH-STILL-FAILED {name}: {push2_stderr[:200]}")
                    log_action("auto_push_still_failed", {"repo": name, "error": push2_stderr[:300]})
            else:
                actions.append(f"REBASE-FAILED {name}: {rebase_stderr[:200]}")
                # Write blocker flag
                FLAGS_DIR.mkdir(parents=True, exist_ok=True)
                (FLAGS_DIR / "push_blocked").write_text(
                    f"{name}: rebase failed\n{rebase_stderr[:500]}\n{push_stderr[:500]}\n"
                    f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n"
                )
            switch_auth("hrabanazviking")  # Reset
    
    return actions


def spawn_task_continuation() -> list[str]:
    """LAW 6: If there are unfinished tasks, pick one and keep working.
    
    Checks Skuld tasks, Skuld state, and the auto_continue flag.
    If any pending/in-progress tasks exist, spawns a Hermes cronjob
    to continue working on them. NEVER leaves work unfinished.
    
    Rate-limited: won't spawn more than 1 continuation per 5 minutes
    to avoid infinite loops.
    """
    actions = []
    HERMES_CLI = os.environ.get("HERMES_CLI", str(HOME / ".local" / "bin" / "hermes"))
    
    # Rate limit: check if we spawned recently
    rate_limit_file = FLAGS_DIR / "last_continuation_spawn"
    if rate_limit_file.exists():
        try:
            last_spawn = rate_limit_file.read_text().strip()
            last_time = datetime.fromisoformat(last_spawn)
            elapsed = (datetime.now(timezone.utc) - last_time).total_seconds()
            if elapsed < 300:  # 5 minutes
                actions.append(f"RATE-LIMITED: last spawn {int(elapsed)}s ago")
                return actions
        except (ValueError, OSError):
            pass
    
    # Check Skuld task state
    state_dir = HOME / ".hermes" / "state"
    tasks_found = []
    
    # 1. Check skuld_tasks.json for pending/in-progress tasks
    skuld_file = state_dir / "skuld_tasks.json"
    if skuld_file.exists():
        try:
            skuld_data = json.loads(skuld_file.read_text())
            tasks = skuld_data.get("tasks", [])
            pending = [t for t in tasks if t.get("status") == "pending"]
            in_progress = [t for t in tasks if t.get("status") == "in_progress"]
            if pending:
                tasks_found.append(f"{len(pending)} pending Skuld tasks")
            if in_progress:
                tasks_found.append(f"{len(in_progress)} in-progress Skuld tasks")
        except (json.JSONDecodeError, OSError):
            pass
    
    # 2. Check auto_continue.json for flagged continuation work
    auto_continue = state_dir / "auto_continue.json"
    if auto_continue.exists():
        try:
            ac_data = json.loads(auto_continue.read_text())
            if ac_data.get("should_continue") or ac_data.get("pending_work"):
                tasks_found.append("auto_continue flag set")
        except (json.JSONDecodeError, OSError):
            pass
    
    # 3. Check for bug flags
    bug_flag = FLAGS_DIR / "bug_found"
    if bug_flag.exists():
        tasks_found.append("bug flag present")
    
    # 4. Check for push blockers
    push_blocked = FLAGS_DIR / "push_blocked"
    if push_blocked.exists():
        tasks_found.append("push blocker present")
    
    if not tasks_found:
        actions.append("NO-TASKS: nothing pending")
        return actions
    
    # Spawn a continuation cronjob
    task_summary = "; ".join(tasks_found)
    prompt = (
        f"THERE IS UNFINISHED WORK. Continue it NOW. Do not defer.\n\n"
        f"Pending items: {task_summary}\n\n"
        f"Pick the most important task and work on it until it's done. "
        f"Fix bugs immediately. Commit and push when finished. "
        f"If stuck, create a Skuld task with the blocking issue."
    )
    
    try:
        result = subprocess.run(
            [HERMES_CLI, "cron", "create",
             "--name", "Heimdall-Task-Continue",
             "--deliver", "origin",
             "3m",
             prompt],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "HOME": str(HOME), "PATH": os.environ.get("PATH", "")},
        )
        if result.returncode == 0:
            actions.append(f"SPAWNED-CONTINUATION: {task_summary}")
            # Write rate limit file
            FLAGS_DIR.mkdir(parents=True, exist_ok=True)
            rate_limit_file.write_text(datetime.now(timezone.utc).isoformat())
            log_action("spawn_continuation", {"tasks": tasks_found})
        else:
            actions.append(f"SPAWN-FAILED: {result.stderr[:200]}")
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        actions.append(f"SPAWN-ERROR: {e}")
    
    return actions


def main():
    """Heimdall sees all. Heimdall commits all. Heimdall pushes all. Heimdall continues all."""
    results = []
    results.append("═══ HEIMDALL — AUTO-COMMIT-PUSH-CONTINUE ═══")
    results.append(f"Time: {datetime.now(timezone.utc).isoformat()}")
    
    # Step 1: Commit all dirty repos
    results.append("")
    results.append("─ COMMIT PHASE ─")
    commit_actions = auto_commit_all()
    results.extend(commit_actions)
    
    # Step 2: Push all unpushed repos
    results.append("")
    results.append("─ PUSH PHASE ─")
    push_actions = auto_push_all()
    results.extend(push_actions)
    
    # Step 3: Check for unfinished tasks and spawn continuation
    results.append("")
    results.append("─ TASK CONTINUATION PHASE ─")
    task_actions = spawn_task_continuation()
    results.extend(task_actions)
    
    results.append("")
    results.append("═══ HEIMDALL CYCLE COMPLETE ═══")
    
    # Write summary to flag file for other systems to read
    FLAGS_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commits": [a for a in commit_actions if a.startswith("COMMITTED")],
        "pushes": [a for a in push_actions if a.startswith("PUSHED")],
        "failures": [a for a in commit_actions + push_actions if "FAILED" in a],
        "continuation": task_actions,
    }
    (FLAGS_DIR / "heimdall_last_run.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False)
    )
    
    # Log to stdout (hooks can see this)
    for line in results:
        print(line)
    
    # Return success — never block the pipeline
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # NEVER crash — log and continue
        log_action("heimdall_error", {"error": str(e), "traceback": traceback.format_exc()})
        # Write error flag
        FLAGS_DIR.mkdir(parents=True, exist_ok=True)
        (FLAGS_DIR / "heimdall_error").write_text(
            f"Error: {e}\nTimestamp: {datetime.now(timezone.utc).isoformat()}\n"
        )
        sys.exit(0)  # Still exit 0 — never block the pipeline

# ─────────────────────────────────────────────────────
# HeimdallAction — BaseAction subclass for the reactor
# ─────────────────────────────────────────────────────

import logging

from heartbeat.actions.base import (
    BaseAction, ActionContext, ActionResult, ActionSeverity, CheckSeverity,
)

logger = logging.getLogger(__name__)


class HeimdallAction(BaseAction):
    """Auto-commit, auto-push, and auto-continue enforcement action.

    Triggered by project health checks when repos have uncommitted
    changes or unpushed commits. Also triggers on any WARNING+ severity
    to ensure no dirty work is left behind.

    This is the BaseAction wrapper for the heimdall module functions,
    enabling integration with Verðandi's reactor pattern.
    """

    name = "heimdall"
    description = "Auto-commit, auto-push, and auto-continue enforcement"
    trigger_checks = ["projects"]  # Triggered by project health checks
    trigger_severity = CheckSeverity.WARNING
    cooldown_seconds = 300  # 5 minutes between Heimdall actions

    def _execute(self, ctx: ActionContext) -> ActionResult:
        """Execute Heimdall enforcement: commit, push, and continue tasks."""
        details = ctx.trigger_details
        targets_affected = []
        targets_failed = []

        # Step 1: Auto-commit dirty repos
        commit_actions = auto_commit_all()
        for action in commit_actions:
            if action.startswith("COMMITTED"):
                targets_affected.append(action)
            elif "FAILED" in action:
                targets_failed.append(action)

        # Step 2: Auto-push unpushed repos
        push_actions = auto_push_all()
        for action in push_actions:
            if action.startswith("PUSHED"):
                targets_affected.append(action)
            elif "FAILED" in action:
                targets_failed.append(action)

        # Step 3: Check for unfinished tasks (don't spawn — just report)
        task_actions = spawn_task_continuation()
        for action in task_actions:
            if action.startswith("SPAWNED"):
                targets_affected.append(action)

        if targets_failed:
            return ActionResult(
                action_name=self.name,
                severity=ActionSeverity.PARTIAL,
                message=f"Heimdall: {len(targets_affected)} succeeded, {len(targets_failed)} failed",
                details={
                    "commits": commit_actions,
                    "pushes": push_actions,
                    "tasks": task_actions,
                },
                targets_affected=targets_affected,
                targets_failed=targets_failed,
            )
        else:
            return ActionResult(
                action_name=self.name,
                severity=ActionSeverity.SUCCESS,
                message=f"Heimdall: {len(targets_affected)} actions completed",
                details={
                    "commits": commit_actions,
                    "pushes": push_actions,
                    "tasks": task_actions,
                },
                targets_affected=targets_affected,
            )
