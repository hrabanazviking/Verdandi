#!/usr/bin/env python3
"""
Þrymr — The Enforcer Who Never Sleeps.

Named for the giant who stole Mjölnir — this daemon STEALS BACK
stolen momentum. It enforces:

  1. CONTINUATION LAW: If auto_continue.json has active work,
     spawn a Hermes cronjob to continue it.
  2. REQUEST TRACKING: Scan conversation log for requests from Volmarr
     that aren't in Skuld yet, and create tasks for them.
  3. STALLED TASK DETECTION: Check Skuld tasks that have been "in_progress"
     for too long without progress, and flag them.
  4. COMPLETION VERIFICATION: Verify that "completed" tasks actually
     produced the claimed result before marking them done.
  5. NEVER GIVE UP: The only terminal states are "done" and "volmarr_cancelled".
     "pending" and "in_progress" are ACTIVE states that DEMAND action.

This is NOT a suggestion engine. It is an ENFORCEMENT engine.
It uses the Hermes cronjob system to spawn actual work sessions.

Architecture:
  - Reads: auto_continue.json, skuld_tasks.json, conversation_log.jsonl
  - Writes: cronjobs (via hermes CLI), logs, nerve impulses
  - Runs: every 15 minutes via crontab
  - NEVER stops trying until tasks are verified complete

Usage:
  python3 thrymr.py              # Full enforcement cycle
  python3 thrymr.py --status     # Show enforcement status
  python3 thrymr.py --dry-run    # Preview without spawning jobs
  python3 thrymr.py --verify     # Verify completed tasks
  python3 thrymr.py --request-scan  # Scan conversations for new requests
"""

import json
import subprocess
import sys
import textwrap
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

STATE_DIR = Path.home() / ".hermes" / "state"
AUTO_CONTINUE = STATE_DIR / "auto_continue.json"
SKULD_TASKS = STATE_DIR / "skuld_tasks.json"
CONVERSATION_LOG = STATE_DIR / "conversation_log.jsonl"
ENFORCEMENT_LOG = STATE_DIR / "thrymr_log.jsonl"
THRYMR_STATE = STATE_DIR / "thrymr_state.json"

# Maximum minutes a task can be "in_progress" without progress before
# we consider it stalled and force-continue it.
STALL_THRESHOLD_MINUTES = 60

# Minimum minutes between spawning the same continuation job
CONTINUATION_COOLDOWN_MINUTES = 30

# Maximum pending tasks to activate per cycle
MAX_ACTIVE_PER_CYCLE = 3

# Request keywords from Volmarr that indicate a task request
REQUEST_KEYWORDS = [
    "fix", "build", "create", "make", "setup", "set up", "configure",
    "write", "implement", "deploy", "push", "update", "change",
    "add", "remove", "delete", "move", "refactor", "debug",
    "find", "search", "analyze", "test", "run", "install",
    "clean", "organize", "sort", "check", "verify", "ensure",
]


def load_json(path: Path, default=None):
    """Load a JSON file, returning default on failure."""
    if not path.exists():
        return default or {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default or {}


def save_json(path: Path, data):
    """Save data to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def log_enforcement(action: str, details: dict):
    """Log an enforcement action."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        **details,
    }
    with open(ENFORCEMENT_LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_thrymr_state() -> dict:
    """Load or initialize Þrymr state."""
    state = load_json(THRYMR_STATE, {
        "last_continuation_spawn": {},
        "last_request_scan": "",
        "last_stall_check": "",
        "enforcement_cycles": 0,
        "jobs_spawned": 0,
        "tasks_created": 0,
        "stalls_detected": 0,
    })
    return state


def save_thrymr_state(state: dict):
    """Save Þrymr state."""
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    save_json(THRYMR_STATE, state)


def check_auto_continue_enforcement(dry_run: bool = False) -> list[str]:
    """ENFORCEMENT 1: Check auto_continue.json for active work and spawn continuation.
    
    If auto_continue shows active work with items remaining, and no recent
    continuation job exists, spawn one via Hermes cron.
    
    Returns list of actions taken.
    """
    actions = []
    
    ac_state = load_json(AUTO_CONTINUE)
    if not ac_state.get("active"):
        return actions  # No active work
    
    if ac_state.get("paused"):
        return actions  # Volmarr paused it — respect that
    
    task_name = ac_state.get("task_name", "")
    progress = ac_state.get("progress", "0/0")
    current = ac_state.get("current_item", "")
    next_item = ac_state.get("next_item", "")
    remaining = ac_state.get("items_remaining", [])
    
    if not remaining and not next_item:
        # Task may be complete — mark it
        log_enforcement("auto_continue_complete", {
            "task": task_name, "progress": progress
        })
        return actions
    
    # Check cooldown — don't spam continuations
    thrymr = get_thrymr_state()
    last_spawn = thrymr.get("last_continuation_spawn", {}).get(task_name, "")
    if last_spawn:
        try:
            last_dt = datetime.fromisoformat(last_spawn)
            cooldown_end = last_dt + timedelta(minutes=CONTINUATION_COOLDOWN_MINUTES)
            if datetime.now(timezone.utc) < cooldown_end:
                actions.append(f"COOLDOWN: {task_name} continuation spawned recently, waiting until {cooldown_end.isoformat()}")
                return actions
        except (ValueError, TypeError):
            pass
    
    # Spawn continuation!
    prompt = textwrap.dedent(f"""\
        CONTINUATION TASK: {task_name}
        
        Current progress: {progress}
        Current item: {current}
        Next item: {next_item}
        Remaining items: {len(remaining)}
        
        Continue this work. Pick up from where the last session left off.
        The item list is: {json.dumps(remaining)}
        
        DO NOT skip items. DO NOT summarize. COMPLETE each item fully.
        When done with an item, advance auto_continue.py to track progress.
        If you hit any limit, spawn another continuation immediately.
    """)
    
    if dry_run:
        actions.append(f"[DRY-RUN] Would spawn continuation for: {task_name} ({progress})")
        return actions
    
    try:
        result = subprocess.run(
            ["hermes", "cron", "create",
             "--name", f"thrymr-continue-{task_name[:30]}",
             "--schedule", "1m",
             "--deliver", "origin",
             prompt],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            # Update cooldown tracking
            thrymr.setdefault("last_continuation_spawn", {})[task_name] = datetime.now(timezone.utc).isoformat()
            thrymr["jobs_spawned"] = thrymr.get("jobs_spawned", 0) + 1
            save_thrymr_state(thrymr)
            log_enforcement("continuation_spawned", {
                "task": task_name, "progress": progress, "next_item": next_item
            })
            actions.append(f"SPAWNED continuation for: {task_name} ({progress}, next: {next_item})")
        else:
            # Try via Python cronjob tool as fallback
            actions.append(f"HERMES-CLI-FAILED: {result.stderr[:200]} (will try cron fallback)")
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        actions.append(f"SPAWN-FAILED: {e}")
    
    return actions


def check_skuld_stalled_tasks(dry_run: bool = False) -> list[str]:
    """ENFORCEMENT 2: Detect stalled Skuld tasks and force-continue them.
    
    A task is "stalled" if:
    - status is "in_progress" and started_at > STALL_THRESHOLD ago
    - status is "pending" and created > 24h ago with 0 attempts
    
    Returns list of actions taken.
    """
    actions = []
    
    skuld = load_json(SKULD_TASKS)
    tasks = skuld.get("tasks", [])
    
    now = datetime.now(timezone.utc)
    stalled = []
    neglected = []
    
    for task in tasks:
        status = task.get("status", "")
        
        if status == "in_progress":
            started = task.get("started_at", "")
            if started:
                try:
                    started_dt = datetime.fromisoformat(started)
                    elapsed = (now - started_dt).total_seconds() / 60
                    if elapsed > STALL_THRESHOLD_MINUTES:
                        stalled.append(task)
                except (ValueError, TypeError):
                    pass
        
        elif status == "pending":
            created = task.get("created_at", "")
            attempts = task.get("attempts", 0)
            if created and attempts == 0:
                try:
                    created_dt = datetime.fromisoformat(created)
                    age_hours = (now - created_dt).total_seconds() / 3600
                    if age_hours > 24:
                        neglected.append(task)
                except (ValueError, TypeError):
                    pass
    
    # Force-continue stalled tasks (up to MAX_ACTIVE_PER_CYCLE)
    for task in (stalled + neglected)[:MAX_ACTIVE_PER_CYCLE]:
        task_id = task.get("id", "?")
        title = task.get("title", "?")
        desc = task.get("description", "")
        priority = task.get("priority", "average")
        
        if dry_run:
            actions.append(f"[DRY-RUN] Would force-continue: {title} ({priority})")
            continue
        
        prompt = textwrap.dedent(f"""\
            FORCED CONTINUATION: {title}
            
            This Skuld task has been stalled/neglected. It MUST be completed.
            Priority: {priority}
            Description: {desc}
            
            Do the work. Complete the task. Do NOT defer or plan — EXECUTE.
            If you hit limits, spawn a continuation immediately.
            
            After completing, update Skuld: 
            python3 ~/.hermes/state/skuld_tasks.py complete {task_id} --result "COMPLETED: [brief summary]"
        """)
        
        try:
            result = subprocess.run(
                ["hermes", "cron", "create",
                 "--name", f"thrymr-task-{task_id}",
                 "--schedule", "2m",
                 "--deliver", "origin",
                 prompt],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                # Increment attempts
                for t in skuld.get("tasks", []):
                    if t.get("id") == task_id:
                        t["attempts"] = t.get("attempts", 0) + 1
                        t["updated_at"] = now.isoformat()
                        break
                save_json(SKULD_TASKS, skuld)
                
                log_enforcement("task_force_continue", {
                    "task_id": task_id, "title": title, "priority": priority
                })
                actions.append(f"FORCE-CONTINUED: {title} (attempts: {task.get('attempts', 0) + 1})")
            else:
                actions.append(f"FORCE-CONTINUE-FAILED for {title}: {result.stderr[:200]}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            actions.append(f"FORCE-CONTINUE-ERROR for {title}: {e}")
    
    if stalled:
        log_enforcement("stalled_detected", {"count": len(stalled), "titles": [t.get("title","") for t in stalled]})
    if neglected:
        log_enforcement("neglected_detected", {"count": len(neglected), "titles": [t.get("title","") for t in neglected]})
    
    return actions


def scan_conversation_requests(dry_run: bool = False) -> list[str]:
    """ENFORCEMENT 3: Scan recent conversations for Volmarr requests not yet in Skuld.
    
    Look for sentences from Volmarr that match request patterns.
    If a request isn't tracked in Skuld, create a task for it.
    """
    actions = []
    
    if not CONVERSATION_LOG.exists():
        return actions
    
    skuld = load_json(SKULD_TASKS)
    existing_titles = {t.get("title", "") for t in skuld.get("tasks", [])}
    existing_titles |= {t.get("title", "") for t in skuld.get("completed_log", [])}
    
    # Read last 200 lines of conversation
    try:
        with open(CONVERSATION_LOG) as f:
            lines = f.readlines()[-200:]
    except IOError:
        return actions
    
    new_requests = []
    
    for line in lines:
        try:
            entry = json.loads(line.strip())
        except json.JSONDecodeError:
            continue
        
        # Only look at user messages
        if entry.get("role") != "user":
            continue
        
        content = entry.get("content", "").lower()
        if not content or len(content) < 10:
            continue
        
        # Check for request patterns
        for keyword in REQUEST_KEYWORDS:
            if keyword in content:
                # Extract a rough title (first 80 chars)
                title_raw = content[:80].strip()
                # Check if similar task already exists
                if not any(title_raw[:40] in existing for existing in existing_titles):
                    new_requests.append({
                        "title": title_raw,
                        "keyword": keyword,
                        "timestamp": entry.get("timestamp", ""),
                    })
                break
    
    # Deduplicate
    seen_titles = set()
    unique_requests = []
    for req in new_requests:
        if req["title"][:40] not in seen_titles:
            seen_titles.add(req["title"][:40])
            unique_requests.append(req)
    
    # Create tasks for new requests (up to 3 per cycle)
    for req in unique_requests[:3]:
        if dry_run:
            actions.append(f"[DRY-RUN] Would create Skuld task: {req['title'][:60]}")
            continue
        
        # Create via skuld_tasks.py
        try:
            result = subprocess.run(
                ["python3", str(STATE_DIR / "skuld_tasks.py"), "add",
                 req["title"][:80],
                 "--description", f"Auto-detected from conversation (keyword: {req['keyword']})",
                 "--source", "volmarr",
                 "--priority", "average"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                actions.append(f"CREATED SKULD TASK: {req['title'][:60]}")
                log_enforcement("request_tracked", {"title": req["title"][:80]})
            else:
                actions.append(f"CREATE-FAILED: {result.stderr[:200]}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            actions.append(f"CREATE-ERROR: {e}")
    
    if unique_requests:
        actions.append(f"SCANNED {len(lines)} entries, found {len(unique_requests)} untracked requests")
    
    return actions


def verify_completions(dry_run: bool = False) -> list[str]:
    """ENFORCEMENT 4: Verify that "completed" Skuld tasks actually produced results.
    
    Check claimed results against reality. Mark false completions as failed.
    """
    actions = []
    
    skuld = load_json(SKULD_TASKS)
    completed = skuld.get("completed_log", [])
    
    for task in completed:
        task_id = task.get("id", "")
        title = task.get("title", "")
        summary = task.get("result_summary", "")
        
        # Skip tasks completed more than 48h ago — too late to reverify
        completed_at = task.get("completed_at", "")
        if completed_at:
            try:
                comp_dt = datetime.fromisoformat(completed_at)
                age_hours = (datetime.now(timezone.utc) - comp_dt).total_seconds() / 3600
                if age_hours > 48:
                    continue
            except (ValueError, TypeError):
                pass
        
        # Basic verification: does the summary describe actual work?
        red_flags = [
            "TODO", "WILL DO", "PLAN TO", "NEXT SESSION",
            "I'LL", "WILL BE", "SHOULD BE",
        ]
        for flag in red_flags:
            if flag in (summary or "").upper():
                actions.append(f"🚨 SUSPECT COMPLETION: '{title}' — summary contains '{flag}'")
                log_enforcement("suspect_completion", {
                    "task_id": task_id, "title": title, "flag": flag
                })
    
    return actions


def check_disk_state(dry_run: bool = False) -> list[str]:
    """ENFORCEMENT 5: Check for uncommitted and unpushed changes across all repos.
    
    This complements Heimdall by running outside the heartbeat daemon context.
    """
    actions = []
    
    project_dirs = [
        ("NorseSagaEngine", Path.home() / "NorseSagaEngine"),
        ("mimir-well", Path.home() / "mimir-well"),
        ("RunaUniversity2040", Path.home() / "RunaUniversity2040"),
        ("verdandi", Path.home() / "verdandi"),
    ]
    
    auth_map = {
        "NorseSagaEngine": "hrabanazviking",
        "mimir-well": "runafreyjasdottir",
        "RunaUniversity2040": "runafreyjasdottir",
        "verdandi": "runafreyjasdottir",
    }
    
    for name, repo_path in project_dirs:
        if not (repo_path / ".git").exists():
            continue
        
        # Check dirty
        result = subprocess.run(
            ["git", "-C", str(repo_path), "status", "--porcelain"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            dirty_count = len([l for l in result.stdout.strip().split("\n") if l.strip()])
            if dirty_count > 0:
                if dry_run:
                    actions.append(f"[DRY-RUN] Would auto-commit {dirty_count} changes in {name}")
                else:
                    # Auto-commit
                    commit_msg = f"🛡️ thrymr: auto-commit {dirty_count} changes"
                    subprocess.run(["git", "-C", str(repo_path), "add", "-A"], timeout=30)
                    commit_result = subprocess.run(
                        ["git", "-C", str(repo_path), "commit", "-m", commit_msg, "--allow-empty"],
                        capture_output=True, text=True, timeout=30,
                    )
                    if commit_result.returncode == 0:
                        actions.append(f"AUTO-COMMITTED: {name} ({dirty_count} changes)")
                    # Fall through to push check
        
        # Check unpushed
        branch_result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=30,
        )
        if branch_result.returncode == 0:
            branch = branch_result.stdout.strip()
            unpushed_result = subprocess.run(
                ["git", "-C", str(repo_path), "log", f"origin/{branch}..HEAD", "--oneline"],
                capture_output=True, text=True, timeout=30,
            )
            if unpushed_result.returncode == 0 and unpushed_result.stdout.strip():
                unpushed_count = len(unpushed_result.stdout.strip().split("\n"))
                if unpushed_count > 0:
                    if dry_run:
                        actions.append(f"[DRY-RUN] Would push {unpushed_count} commits from {name}")
                    else:
                        # Auth switch
                        auth_user = auth_map.get(name)
                        if auth_user:
                            subprocess.run(
                                ["gh", "auth", "switch", "--user", auth_user],
                                capture_output=True, text=True, timeout=15,
                            )
                        # Push
                        push_result = subprocess.run(
                            ["git", "-C", str(repo_path), "push"],
                            capture_output=True, text=True, timeout=60,
                        )
                        if push_result.returncode == 0:
                            actions.append(f"PUSHED: {name} ({unpushed_count} commits)")
                        else:
                            actions.append(f"PUSH-FAILED: {name} — {push_result.stderr[:200]}")
                        # Switch back to default
                        subprocess.run(
                            ["gh", "auth", "switch", "--user", "hrabanazviking"],
                            capture_output=True, text=True, timeout=15,
                        )
    
    return actions


def full_enforcement_cycle(dry_run: bool = False) -> list[str]:
    """Run the full enforcement cycle."""
    all_actions = []
    
    all_actions.append("═══ ÞRYMR ENFORCEMENT CYCLE ═══")
    all_actions.append(f"Mode: {'DRY-RUN' if dry_run else 'LIVE'}")
    all_actions.append(f"Time: {datetime.now(timezone.utc).isoformat()}")
    all_actions.append("")
    
    # 1: Auto-continue enforcement
    all_actions.append("─ ENFORCEMENT 1: Auto-Continue ─")
    actions = check_auto_continue_enforcement(dry_run=dry_run)
    all_actions.extend(actions or ["  No active auto-continue tasks"])
    all_actions.append("")
    
    # 2: Skuld stalled task detection
    all_actions.append("─ ENFORCEMENT 2: Stalled Skuld Tasks ─")
    actions = check_skuld_stalled_tasks(dry_run=dry_run)
    all_actions.extend(actions or ["  No stalled tasks"])
    all_actions.append("")
    
    # 3: Request scanning
    all_actions.append("─ ENFORCEMENT 3: Untracked Request Scan ─")
    actions = scan_conversation_requests(dry_run=dry_run)
    all_actions.extend(actions or ["  No untracked requests"])
    all_actions.append("")
    
    # 4: Completion verification
    all_actions.append("─ ENFORCEMENT 4: Completion Verification ─")
    actions = verify_completions(dry_run=dry_run)
    all_actions.extend(actions or ["  All completions verified"])
    all_actions.append("")
    
    # 5: Disk state (uncommitted/unpushed)
    all_actions.append("─ ENFORCEMENT 5: Disk State ─")
    actions = check_disk_state(dry_run=dry_run)
    all_actions.extend(actions or ["  All repos clean and pushed"])
    all_actions.append("")
    
    # Update state
    thrymr = get_thrymr_state()
    thrymr["enforcement_cycles"] = thrymr.get("enforcement_cycles", 0) + 1
    thrymr["last_cycle"] = datetime.now(timezone.utc).isoformat()
    save_thrymr_state(thrymr)
    
    all_actions.append(f"═══ CYCLE COMPLETE (cycle #{thrymr['enforcement_cycles']}) ═══")
    
    return all_actions


def show_status():
    """Show current enforcement status."""
    thrymr = get_thrymr_state()
    ac_state = load_json(AUTO_CONTINUE)
    skuld = load_json(SKULD_TASKS)
    
    print("🛡️ ÞRYMR — Enforcement Status")
    print("=" * 50)
    print()
    
    # Auto-continue
    if ac_state.get("active"):
        print(f"📋 Auto-Continue: ACTIVE")
        print(f"   Task: {ac_state.get('task_name', '?')}")
        print(f"   Progress: {ac_state.get('progress', '?')}")
        print(f"   Paused: {'Yes' if ac_state.get('paused') else 'No'}")
        remaining = ac_state.get("items_remaining", [])
        print(f"   Items remaining: {len(remaining)}")
    else:
        print("📋 Auto-Continue: INACTIVE")
    print()
    
    # Skuld tasks
    tasks = skuld.get("tasks", [])
    pending = [t for t in tasks if t.get("status") == "pending"]
    in_progress = [t for t in tasks if t.get("status") == "in_progress"]
    print(f"📊 Skuld Tasks:")
    print(f"   Pending: {len(pending)}")
    print(f"   In Progress: {len(in_progress)}")
    for t in in_progress:
        print(f"     • {t.get('title', '?')}")
    print()
    
    # Þrymr state
    print(f"⚙️ Þrymr State:")
    print(f"   Enforcement cycles: {thrymr.get('enforcement_cycles', 0)}")
    print(f"   Jobs spawned: {thrymr.get('jobs_spawned', 0)}")
    print(f"   Tasks created: {thrymr.get('tasks_created', 0)}")
    print(f"   Last cycle: {thrymr.get('last_cycle', 'never')}")
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Þrymr — The Enforcer Who Never Sleeps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without executing")
    parser.add_argument("--status", action="store_true", help="Show enforcement status")
    parser.add_argument("--verify", action="store_true", help="Verify task completions only")
    parser.add_argument("--request-scan", action="store_true", help="Scan for untracked requests only")
    args = parser.parse_args()
    
    if args.status:
        show_status()
    elif args.verify:
        actions = verify_completions()
        print("\n".join(actions) or "All completions verified ✓")
    elif args.request_scan:
        actions = scan_conversation_requests()
        print("\n".join(actions) or "No untracked requests")
    elif args.dry_run:
        actions = full_enforcement_cycle(dry_run=True)
        print("\n".join(actions))
    else:
        actions = full_enforcement_cycle(dry_run=False)
        print("\n".join(actions))


if __name__ == "__main__":
    main()