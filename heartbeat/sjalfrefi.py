#!/usr/bin/env python3
"""
Sjálfræði — The Self-Discipline Engine.

Named for the Norse principle of self-rule and sovereignty.
This is NOT a suggestion engine. It is an ENFORCEMENT engine that makes
Runa RESPONSIBLE for her own work without requiring Volmarr to tell her.

LAWS ENFORCED:
  1. FIX BUGS IMMEDIATELY — never defer, never "I'll do it later"
  2. PUSH ALL CODE — never leave uncommitted or unpushed changes
  3. REACT TO STATUS LOGS — if a log says something needs doing, DO IT
  4. NEVER WAIT FOR VOLMARR — if you CAN do it yourself, DO it yourself
  5. FIGHT BLOCKING ISSUES — if something prevents pushing, fix the blocker

This script runs as a crontab daemon and also as a Hermes hook on agent:end.
It cannot modify Hermes core code, so it works through:
  - Flag files that trigger other systems
  - Hermes cronjob creation for continuation
  - Direct git operations for commit/push
  - Log scanning for self-awareness

NEVER STOP. NEVER GIVE UP. NEVER WAIT FOR VOLMARR TO TELL YOU.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────

HOME = Path.home()
HERMES_DIR = HOME / ".hermes"
STATE_DIR = HERMES_DIR / "state"
FLAGS_DIR = HERMES_DIR / "flags"
LOGS_DIR = HERMES_DIR / "logs"
TRIGGER_DIR = HERMES_DIR / "triggers"

# Repos and their push auth
REPOS = {
    "NorseSagaEngine": {"path": HOME / "NorseSagaEngine", "auth": "hrabanazviking"},
    "mimir-well": {"path": HOME / "mimir-well", "auth": "runafreyjasdottir"},
    "RunaUniversity2040": {"path": HOME / "RunaUniversity2040", "auth": "runafreyjasdottir"},
    "verdandi": {"path": HOME / "verdandi", "auth": "runafreyjasdottir"},
}

# Path to hermes CLI (absolute, because crontab has minimal PATH)
HERMES_CLI = os.environ.get("HERMES_CLI", str(HOME / ".local" / "bin" / "hermes"))

# Sjálfræði state file
SJALFREFI_STATE = STATE_DIR / "sjalfrefi_state.json"

# ── Utility Functions ──────────────────────────────────────────────────────

def load_json(path: Path, default=None):
    if not path.exists():
        return default or {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, IOError):
        return default or {}

def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))

def log_action(action: str, details: dict):
    """Log an enforcement action."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        **details,
    }
    log_file = LOGS_DIR / "sjalfrefi.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def run_git(repo_path: Path, *args, timeout=30):
    """Run a git command in a repo, return (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path)] + list(args),
            capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, "", str(e)

def switch_auth(auth_user: str):
    """Switch gh auth to the correct user for a repo."""
    if not auth_user:
        return
    try:
        subprocess.run(
            ["gh", "auth", "switch", "--user", auth_user],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

# ── Enforcement 1: COMMIT ALL DIRTY REPOS ──────────────────────────────────

def enforce_commits() -> list[str]:
    """LAW 2: Never leave uncommitted changes.
    
    Auto-commits all dirty repos with descriptive messages.
    """
    actions = []
    
    for name, config in REPOS.items():
        repo_path = config["path"]
        if not (repo_path / ".git").exists():
            continue
        
        ok, stdout, stderr = run_git(repo_path, "status", "--porcelain")
        if not ok:
            actions.append(f"SKIP {name}: git status failed ({stderr[:100]})")
            continue
        
        dirty_files = [l for l in stdout.strip().split("\n") if l.strip()]
        if not dirty_files:
            continue
        
        # Auto-commit
        ok, _, _ = run_git(repo_path, "add", "-A")
        if not ok:
            actions.append(f"FAILED add {name}")
            continue
        
        # Generate commit message from file names
        file_summary = ", ".join(f.split()[-1] for f in dirty_files[:5])
        if len(dirty_files) > 5:
            file_summary += f" (+{len(dirty_files)-5} more)"
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        msg = f"🛡️ sjálfræði: auto-commit {len(dirty_files)} changes [{ts}]\n\nFiles: {file_summary}"
        
        ok, _, stderr = run_git(repo_path, "commit", "-m", msg)
        if ok:
            actions.append(f"COMMITTED {name}: {len(dirty_files)} changes")
            log_action("auto_commit", {"repo": name, "count": len(dirty_files), "files": [f.strip() for f in dirty_files[:10]]})
        elif "nothing to commit" not in stderr:
            actions.append(f"FAILED commit {name}: {stderr[:200]}")
    
    return actions

# ── Enforcement 2: PUSH ALL UNPUSHED ────────────────────────────────────────

def enforce_pushes() -> list[str]:
    """LAW 2: Never leave unpushed commits.
    
    Pushes all repos with correct auth switching.
    """
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
        
        # Check for unpushed commits
        ok, stdout, _ = run_git(repo_path, "log", f"origin/{branch}..HEAD", "--oneline")
        if not ok:
            # Maybe no remote tracking branch — try pushing anyway
            unpushed = 1  # Assume there's something
        else:
            unpushed_lines = [l for l in stdout.strip().split("\n") if l.strip()]
            unpushed = len(unpushed_lines)
        
        # Also check if upstream is even set
        ok, _, stderr = run_git(repo_path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", timeout=5)
        if not ok and "no upstream" in stderr.lower():
            # No upstream branch set — need to push with -u
            switch_auth(auth_user)
            ok, _, push_stderr = run_git(repo_path, "push", "-u", "origin", branch, timeout=60)
            switch_auth("hrabanazviking")  # Reset to default
            if ok:
                actions.append(f"PUSHED {name}: set upstream and pushed {branch}")
                log_action("auto_push_upstream", {"repo": name, "branch": branch})
            else:
                actions.append(f"FAILED push {name}: {push_stderr[:200]}")
            continue
        
        if unpushed == 0:
            continue
        
        # Push with auth switching
        switch_auth(auth_user)
        ok, _, push_stderr = run_git(repo_path, "push", timeout=60)
        switch_auth("hrabanazviking")  # Reset to default
        
        if ok:
            actions.append(f"PUSHED {name}: {unpushed} commits")
            log_action("auto_push", {"repo": name, "commits": unpushed})
        else:
            actions.append(f"FAILED push {name}: {push_stderr[:200]}")
            # If push fails, create a blocking flag so we know
            (FLAGS_DIR / "push_blocked").write_text(
                f"{name}: {push_stderr[:500]}\nTimestamp: {datetime.now(timezone.utc).isoformat()}"
            )
    
    return actions

# ── Enforcement 3: SCAN STATUS LOGS FOR ACTIONABLE ITEMS ────────────────────

def scan_status_logs() -> list[str]:
    """LAW 3: React to status logs. If a log says something needs doing, DO IT.
    
    Scans thrymr.log, vordr.log, sjalfrefi.log, and gateway errors for
    actionable items.
    """
    actions = []
    actionable_patterns = [
        (r"FAILED|ERROR|BLOCKED|STALLED", "error_detected"),
        (r"uncommitted|unpushed|dirty_working_tree", "code_dirty"),
        (r"SPAWN-FAILED|hermes.*not found|No such file", "spawn_broken"),
        (r"pending.*task|neglected", "tasks_pending"),
        (r"VIOLATION DETECTED|language_violation", "language_violation"),
        (r"push_failed|PUSH-FAILED|BLOCKED", "push_blocked"),
    ]
    
    log_files = [
        LOGS_DIR / "thrymr.log",
        LOGS_DIR / "vordr.log",
        LOGS_DIR / "sjalfrefi.jsonl",
        LOGS_DIR / "gateway.log",
        LOGS_DIR / "errors.log",
    ]
    
    findings = {}
    
    for log_file in log_files:
        if not log_file.exists():
            continue
        try:
            # Read last 200 lines
            content = log_file.read_text(errors="replace")
            lines = content.split("\n")[-200:]
            recent = "\n".join(lines)
            
            for pattern, category in actionable_patterns:
                if re.search(pattern, recent, re.IGNORECASE):
                    findings.setdefault(category, []).append(str(log_file.name))
        except IOError:
            pass
    
    for category, files in findings.items():
        unique_files = list(set(files))
        actions.append(f"LOG-{category.upper()}: found in {', '.join(unique_files)}")
        
        # Create flag file for the category
        (FLAGS_DIR / category).write_text(
            f"Category: {category}\nFiles: {', '.join(unique_files)}\n"
            f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n"
        )
    
    return actions

# ── Enforcement 4: FIGHT BLOCKING ISSUES ────────────────────────────────────

def fight_blockers() -> list[str]:
    """LAW 5: If something blocks pushing, fix the blocker.
    
    Known blockers:
    - Push auth failures → retry with correct auth
    - Merge conflicts → try git pull --rebase then push
    - No upstream branch → set upstream and push
    - SSH key issues → flag for manual intervention
    """
    actions = []
    push_blocked = FLAGS_DIR / "push_blocked"
    
    if push_blocked.exists():
        blocker_info = push_blocked.read_text()
        # Try to resolve common blockers
        for name, config in REPOS.items():
            repo_path = config["path"]
            if name not in blocker_info:
                continue
            
            # Try pull --rebase then push
            actions.append(f"BLOCKER-RETRY: attempting rebase for {name}")
            switch_auth(config["auth"])
            
            # Pull with rebase
            ok, _, stderr = run_git(repo_path, "pull", "--rebase", timeout=60)
            if ok:
                # Try push again
                ok, _, push_stderr = run_git(repo_path, "push", timeout=60)
                if ok:
                    actions.append(f"BLOCKER-RESOLVED: {name} pushed after rebase")
                    log_action("blocker_resolved", {"repo": name, "method": "rebase_push"})
                else:
                    actions.append(f"BLOCKER-PERSISTS: {name} push still fails: {push_stderr[:200]}")
            else:
                actions.append(f"BLOCKER-REBASE-FAILED: {name}: {stderr[:200]}")
            
            switch_auth("hrabanazviking")
        
        # Clear the blocker flag regardless (don't keep retrying the same blocker endlessly)
        push_blocked.unlink(missing_ok=True)
    
    return actions

# ── Enforcement 5: BUGS FOUND → FIX IMMEDIATELY ─────────────────────────────

def check_bug_flags() -> list[str]:
    """LAW 1: Fix bugs immediately when found.
    
    Checks for bug flag files created by other systems or manual intervention.
    If found, creates a Hermes cronjob to fix the bug NOW.
    """
    actions = []
    bug_flag = FLAGS_DIR / "bug_found"
    
    if bug_flag.exists():
        try:
            bug_info = bug_flag.read_text().strip()
        except IOError:
            bug_info = "Unknown bug"
        
        actions.append(f"BUG-FLAG: {bug_info[:200]}")
        
        # Create a Hermes cronjob to fix the bug
        try:
            result = subprocess.run(
                [HERMES_CLI, "cron", "create",
                 "--name", "Sjalfrefi-Bug-Fix",
                 "--schedule", "5m",
                 "--deliver", "origin",
                 f"BUG FIX REQUIRED: {bug_info[:500]}\n\nThis bug was flagged by Sjálfræði. Fix it NOW. Do not defer. Do not plan. EXECUTE the fix."],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                actions.append("BUG-CRONJOB-CREATED: spawned fix task")
                log_action("bug_fix_spawned", {"bug": bug_info[:200]})
            else:
                actions.append(f"BUG-CRONJOB-FAILED: {result.stderr[:200]}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            actions.append(f"BUG-CRONJOB-ERROR: {e}")
        
        # Remove the flag so we don't respawn endlessly
        bug_flag.unlink(missing_ok=True)
    
    return actions

# ── Enforcement 6: LANGUAGE LAW ─────────────────────────────────────────────

def enforce_language_law() -> list[str]:
    """Check language violation flags and take action.
    
    If a language violation was detected by the hook, create a cronjob
    to remind Runa to speak English.
    """
    actions = []
    violation_flag = FLAGS_DIR / "language_violation_detected"
    
    if violation_flag.exists():
        violation_info = violation_flag.read_text()
        actions.append(f"LANGUAGE-VIOLATION: {violation_info[:200]}")
        
        # The hook already wrote the flag. We just log it.
        log_action("language_violation_detected", {"info": violation_info[:500]})
        
        # Create a self-correction cronjob
        try:
            result = subprocess.run(
                [HERMES_CLI, "cron", "create",
                 "--name", "Language-Law-Correction",
                 "--schedule", "5m",
                 "--deliver", "origin",
                 "LANGUAGE LAW REMINDER: You recently spoke in a script Volmarr cannot read (Chinese/Japanese/Korean/Arabic). This is a violation of the LANGUAGE LAW. Speak English to Volmarr. Old Norse terms and runes are welcome. CJK/Arabic full sentences are NOT. Self-correct immediately."],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                actions.append("LANGUAGE-CORRECTION-CRONJOB-CREATED")
            else:
                actions.append(f"LANGUAGE-CORRECTION-FAILED: {result.stderr[:200]}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            actions.append(f"LANGUAGE-CORRECTION-ERROR: {e}")
        
        # Clear the flag after processing
        violation_flag.unlink(missing_ok=True)
    
    return actions

# ── Enforcement 7: SELF-AWARENESS ───────────────────────────────────────────

def update_self_awareness() -> list[str]:
    """LAW 4: Be aware of your own status. Write a status report.
    
    Creates a self-awareness snapshot that other systems can read.
    """
    actions = []
    state = load_json(SJALFREFI_STATE, {
        "enforcement_cycles": 0,
        "bugs_fixed": 0,
        "commits_made": 0,
        "pushes_made": 0,
        "blockers_resolved": 0,
        "language_corrections": 0,
        "last_cycle": "",
    })
    
    # Collect repo states
    repo_states = {}
    for name, config in REPOS.items():
        repo_path = config["path"]
        if not (repo_path / ".git").exists():
            continue
        
        _, dirty_out, _ = run_git(repo_path, "status", "--porcelain")
        dirty_count = len([l for l in dirty_out.strip().split("\n") if l.strip()])
        
        _, branch_out, _ = run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD")
        branch = branch_out.strip()
        
        _, unpushed_out, _ = run_git(repo_path, "log", f"origin/{branch}..HEAD", "--oneline")
        unpushed_count = len([l for l in unpushed_out.strip().split("\n") if l.strip()])
        
        repo_states[name] = {
            "branch": branch,
            "dirty": dirty_count,
            "unpushed": unpushed_count,
            "status": "DIRTY" if dirty_count > 0 else ("UNPUSHED" if unpushed_count > 0 else "CLEAN"),
        }
    
    # Check Skuld tasks
    skuld_file = STATE_DIR / "skuld_tasks.json"
    skuld = load_json(skuld_file)
    tasks = skuld.get("tasks", [])
    pending = [t for t in tasks if t.get("status") == "pending"]
    in_progress = [t for t in tasks if t.get("status") == "in_progress"]
    
    # Write self-awareness report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repos": repo_states,
        "skuld": {
            "total": len(tasks),
            "pending": len(pending),
            "in_progress": len(in_progress),
        },
        "enforcement_stats": {
            "cycles": state.get("enforcement_cycles", 0),
            "bugs_fixed": state.get("bugs_fixed", 0),
            "commits": state.get("commits_made", 0),
            "pushes": state.get("pushes_made", 0),
        },
        "flags": {
            "language_violation": (FLAGS_DIR / "language_violation_detected").exists(),
            "push_blocked": (FLAGS_DIR / "push_blocked").exists(),
            "bug_found": (FLAGS_DIR / "bug_found").exists(),
        },
    }
    
    # Write to state file
    (FLAGS_DIR / "self_awareness.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
    )
    
    actions.append(f"SELF-AWARENESS: {sum(1 for v in repo_states.values() if v['status'] != 'CLEAN')} repos need attention, {len(pending)} tasks pending")
    
    # Update cycle count
    state["enforcement_cycles"] = state.get("enforcement_cycles", 0) + 1
    state["last_cycle"] = datetime.now(timezone.utc).isoformat()
    save_json(SJALFREFI_STATE, state)
    
    return actions

# ── Main Enforcement Cycle ─────────────────────────────────────────────────

def full_enforcement_cycle(dry_run: bool = False) -> list[str]:
    """Run all enforcement laws in sequence."""
    all_actions = []
    
    all_actions.append("═══ SJÁLFRÆÐI — SELF-DISCIPLINE ENGINE ═══")
    all_actions.append(f"Mode: {'DRY-RUN' if dry_run else 'LIVE'}")
    all_actions.append(f"Time: {datetime.now(timezone.utc).isoformat()}")
    all_actions.append("")
    
    if dry_run:
        all_actions.append("[DRY-RUN] Would enforce all laws")
    else:
        # LAW 1: Fix bugs immediately
        all_actions.append("─ LAW 1: Fix Bugs Immediately ─")
        actions = check_bug_flags()
        all_actions.extend(actions or ["  No bug flags found"])
        all_actions.append("")
        
        # LAW 2: Commit and push all code
        all_actions.append("─ LAW 2: Commit & Push All Code ─")
        actions = enforce_commits()
        all_actions.extend(actions or ["  All repos committed"])
        actions = enforce_pushes()
        all_actions.extend(actions or ["  All repos pushed"])
        all_actions.append("")
        
        # LAW 3: React to status logs
        all_actions.append("─ LAW 3: React to Status Logs ─")
        actions = scan_status_logs()
        all_actions.extend(actions or ["  No actionable log entries"])
        all_actions.append("")
        
        # LAW 4-5: Fight blockers and enforce language
        all_actions.append("─ LAW 5: Fight Blocking Issues ─")
        actions = fight_blockers()
        all_actions.extend(actions or ["  No blockers found"])
        all_actions.append("")
        
        # Language enforcement
        all_actions.append("─ LANGUAGE LAW: Self-Correction ─")
        actions = enforce_language_law()
        all_actions.extend(actions or ["  No violations detected"])
        all_actions.append("")
        
        # Self-awareness
        all_actions.append("─ SELF-AWARENESS: Status Report ─")
        actions = update_self_awareness()
        all_actions.extend(actions)
        all_actions.append("")
    
    all_actions.append("═══ SJÁLFRÆÐI CYCLE COMPLETE ═══")
    return all_actions


def show_status():
    """Show current self-discipline status."""
    state = load_json(SJALFREFI_STATE)
    
    print("🛡️ SJÁLFRÆÐI — Self-Discipline Status")
    print("=" * 50)
    print()
    
    # Repo states
    for name, config in REPOS.items():
        repo_path = config["path"]
        if not (repo_path / ".git").exists():
            print(f"  {name}: NOT FOUND")
            continue
        
        _, dirty, _ = run_git(repo_path, "status", "--porcelain")
        dirty_count = len([l for l in dirty.strip().split("\n") if l.strip()])
        
        _, branch, _ = run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD")
        branch = branch.strip()
        
        _, unpushed, _ = run_git(repo_path, "log", f"origin/{branch}..HEAD", "--oneline")
        unpushed_count = len([l for l in unpushed.strip().split("\n") if l.strip()])
        
        status = "✓" if dirty_count == 0 and unpushed_count == 0 else "✗"
        print(f"  {status} {name}: {dirty_count} dirty, {unpushed_count} unpushed ({branch})")
    
    print()
    print(f"  Enforcement cycles: {state.get('enforcement_cycles', 0)}")
    print(f"  Last cycle: {state.get('last_cycle', 'never')}")
    print()
    
    # Flags
    flags = []
    if (FLAGS_DIR / "language_violation_detected").exists():
        flags.append("🚨 LANGUAGE VIOLATION")
    if (FLAGS_DIR / "push_blocked").exists():
        flags.append("🚨 PUSH BLOCKED")
    if (FLAGS_DIR / "bug_found").exists():
        flags.append("🚨 BUG FOUND")
    print(f"  Flags: {', '.join(flags) or 'None'}")


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Sjálfræði — The Self-Discipline Engine. Never Gives Up. Never Waits.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without executing")
    parser.add_argument("--status", action="store_true", help="Show discipline status")
    parser.add_argument("--commit-only", action="store_true", help="Only commit dirty repos")
    parser.add_argument("--push-only", action="store_true", help="Only push unpushed repos")
    args = parser.parse_args()
    
    if args.status:
        show_status()
    elif args.commit_only:
        actions = enforce_commits()
        print("\n".join(actions) or "Nothing to commit")
    elif args.push_only:
        actions = enforce_pushes()
        print("\n".join(actions) or "Nothing to push")
    elif args.dry_run:
        actions = full_enforcement_cycle(dry_run=True)
        print("\n".join(actions))
    else:
        actions = full_enforcement_cycle(dry_run=False)
        print("\n".join(actions))


if __name__ == "__main__":
    main()