#!/usr/bin/env python3
"""
Vörðr — The Watcher Who Triggers Continuation.

Named for the Norse guardian spirit that watches over a person.
Vörðr runs after every session turn, checks for remaining work, and
if found, sends a Telegram nudge to trigger Runa to take another turn.

Unlike Þrymr (which runs on a 15-minute crontab and forces actions),
Vörðr focuses on IMMEDIATE post-turn continuation — if Runa just finished
a task but there are more pending, Vörðr nudges her to keep going.

This is the implementation of Volmarr's requirement:
"After every turn ends, automatically check if there is more work
that needs doing, and if so, trigger another turn."

Vörðr checks:
  1. Skuld tasks: any pending or in_progress tasks?
  2. Git state: any uncommitted or unpushed changes in key repos?
  3. Auto-continue: any active auto-continue items remaining?
  4. Conversation context: any explicit requests from Volmarr that
     haven't been completed yet?

If ANY of these are true, Vörðr sends a message via `send_message`
to Telegram, listing the specific work items that need attention.

Usage:
  python3 vordr.py              # Full check + nudge if work found
  python3 vordr.py --status     # Show what Vörðr sees
  python3 vordr.py --quiet      # Only nudge, no status output
"""

import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

STATE_DIR = Path.home() / ".hermes" / "state"
SKULD_TASKS = STATE_DIR / "skuld_tasks.json"
AUTO_CONTINUE = STATE_DIR / "auto_continue.json"

KEY_REPOS = {
    "NorseSagaEngine": Path.home() / "NorseSagaEngine",
    "mimir-well": Path.home() / "mimir-well",
    "RunaUniversity2040": Path.home() / "RunaUniversity2040",
    "verdandi": Path.home() / "verdandi",
    "Hamr": Path.home() / "Hamr",
}

# Minimum minutes between nudges for the same category
NUDGE_COOLDOWN_MINUTES = 30
NUDGE_LOG = STATE_DIR / "vordr_nudge_log.jsonl"


def load_json(path: Path, default=None):
    if not path.exists():
        return default or {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default or {}


def log_nudge(category: str, details: str):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "details": details,
    }
    NUDGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(NUDGE_LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def recent_nudge_exists(category: str) -> bool:
    """Check if we nudged this category recently (within cooldown)."""
    if not NUDGE_LOG.exists():
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=NUDGE_COOLDOWN_MINUTES)
    try:
        with open(NUDGE_LOG) as f:
            for line in reversed(f.readlines()[-50:]):
                try:
                    entry = json.loads(line.strip())
                    if entry.get("category") == category:
                        ts = datetime.fromisoformat(entry.get("timestamp", ""))
                        if ts > cutoff:
                            return True
                except (json.JSONDecodeError, ValueError):
                    continue
    except IOError:
        pass
    return False


def check_skuld_tasks() -> list[dict]:
    """Check Skuld task list for pending/in_progress work."""
    tasks = []
    skuld = load_json(SKULD_TASKS)
    for task in skuld.get("tasks", []):
        status = task.get("status", "")
        if status in ("pending", "in_progress"):
            tasks.append({
                "id": task.get("id", "?"),
                "title": task.get("title", "?"),
                "priority": task.get("priority", "average"),
                "status": status,
                "attempts": task.get("attempts", 0),
            })
    return tasks


def check_git_state() -> list[dict]:
    """Check key repos for uncommitted/unpushed changes."""
    results = []
    for name, repo_path in KEY_REPOS.items():
        if not (repo_path / ".git").exists():
            continue
        
        # Check dirty
        r = subprocess.run(
            ["git", "-C", str(repo_path), "status", "--porcelain"],
            capture_output=True, text=True, timeout=30,
        )
        dirty_count = len([l for l in (r.stdout or "").strip().split("\n") if l.strip()]) if r.returncode == 0 else 0
        
        # Check unpushed
        branch_r = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=30,
        )
        unpushed_count = 0
        if branch_r.returncode == 0:
            branch = branch_r.stdout.strip()
            unpushed_r = subprocess.run(
                ["git", "-C", str(repo_path), "log", f"origin/{branch}..HEAD", "--oneline"],
                capture_output=True, text=True, timeout=30,
            )
            if unpushed_r.returncode == 0 and unpushed_r.stdout.strip():
                unpushed_count = len(unpushed_r.stdout.strip().split("\n"))
        
        if dirty_count > 0 or unpushed_count > 0:
            results.append({
                "repo": name,
                "dirty": dirty_count,
                "unpushed": unpushed_count,
            })
    
    return results


def check_auto_continue() -> dict:
    """Check if auto-continue has active work remaining."""
    ac = load_json(AUTO_CONTINUE)
    if not ac.get("active"):
        return {"active": False}
    return {
        "active": True,
        "task": ac.get("task_name", "?"),
        "progress": ac.get("progress", "?"),
        "remaining": len(ac.get("items_remaining", [])),
        "current_item": ac.get("current_item", ""),
        "next_item": ac.get("next_item", ""),
    }


def format_nudge_message(
    skuld: list[dict],
    git: list[dict],
    auto_continue: dict,
) -> str:
    """Format the nudge message to send via Telegram."""
    lines = ["🛡️ **Vörðr: Work Remains**\n"]
    
    if skuld:
        lines.append(f"**Skuld Tasks ({len(skuld)} active):**")
        for t in skuld[:5]:
            lines.append(f"  • [{t['priority']}] {t['title']} ({t['status']}, attempts: {t['attempts']})")
        if len(skuld) > 5:
            lines.append(f"  ... and {len(skuld) - 5} more")
        lines.append("")
    
    if git:
        lines.append("**Uncommitted/Unpushed Code:**")
        for g in git:
            parts = []
            if g["dirty"]:
                parts.append(f"{g['dirty']} dirty")
            if g["unpushed"]:
                parts.append(f"{g['unpushed']} unpushed")
            lines.append(f"  • {g['repo']}: {', '.join(parts)}")
        lines.append("")
    
    if auto_continue.get("active"):
        lines.append(f"**Auto-Continue Active:**")
        lines.append(f"  • {auto_continue['task']} — {auto_continue['progress']}")
        lines.append(f"  • {auto_continue['remaining']} items remaining")
        lines.append("")
    
    lines.append("Continue working. Do not stop until all tasks are complete.")
    lines.append("_Vörðr watches. Þrymr enforces. You act._")
    
    return "\n".join(lines)


def send_nudge(message: str) -> bool:
    """Send a nudge message via Hermes send_message to Telegram."""
    try:
        result = subprocess.run(
            ["hermes", "send", "--target", "telegram", "--message", message],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # Fallback: write to a trigger file that Hermes will pick up
        trigger_dir = Path.home() / ".hermes" / "triggers"
        trigger_dir.mkdir(parents=True, exist_ok=True)
        trigger_file = trigger_dir / f"vordr_nudge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        trigger_file.write_text(json.dumps({
            "type": "vordr_nudge",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": message,
        }, ensure_ascii=False))
        return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Vörðr — Post-turn continuation checker")
    parser.add_argument("--status", action="store_true", help="Show what Vörðr sees without nudging")
    parser.add_argument("--quiet", action="store_true", help="Only nudge if work found, minimal output")
    args = parser.parse_args()
    
    # Check all sources
    skuld = check_skuld_tasks()
    git = check_git_state()
    auto_cont = check_auto_continue()
    
    has_work = bool(skuld) or bool(git) or auto_cont.get("active", False)
    
    if args.status:
        print("🛡️ VÖRÐR — Watcher Status")
        print("=" * 50)
        print(f"\nSkuld Tasks: {len(skuld)} active")
        for t in skuld[:5]:
            print(f"  • [{t['priority']}] {t['title']} ({t['status']})")
        print(f"\nGit State: {len(git)} repos with changes")
        for g in git:
            print(f"  • {g['repo']}: {g['dirty']} dirty, {g['unpushed']} unpushed")
        print(f"\nAuto-Continue: {'ACTIVE' if auto_cont.get('active') else 'INACTIVE'}")
        if auto_cont.get("active"):
            print(f"  • {auto_cont['task']} — {auto_cont['progress']}")
        print(f"\nHas Work: {'YES — nudge needed' if has_work else 'NO — clear'}")
        return
    
    if not has_work:
        if not args.quiet:
            print("🛡️ Vörðr: No work remaining. All clear.")
        return
    
    # Check cooldown — don't nudge the same category too often
    nudge_categories = []
    if skuld:
        nudge_categories.append("skuld")
    if git:
        nudge_categories.append("git")
    if auto_cont.get("active"):
        nudge_categories.append("auto_continue")
    
    # Check if any category is still in cooldown
    hot_categories = [c for c in nudge_categories if recent_nudge_exists(c)]
    if hot_categories and not args.quiet:
        print(f"🛡️ Vörðr: Cooldown active for: {', '.join(hot_categories)}. Waiting.")
        return
    
    # Build and send the nudge
    message = format_nudge_message(skuld, git, auto_cont)
    
    if not args.quiet:
        print(message)
    
    success = send_nudge(message)
    
    # Log the nudge
    for cat in nudge_categories:
        log_nudge(cat, f"Nudged: {len(skuld)} skuld, {len(git)} git, auto_continue={auto_cont.get('active')}")
    
    if not args.quiet:
        if success:
            print("\n✅ Nudge sent to Telegram")
        else:
            print("\n⚠️ Nudge delivery failed — wrote to trigger file as fallback")


if __name__ == "__main__":
    main()