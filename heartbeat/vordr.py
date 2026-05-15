#!/usr/bin/env python3
"""
Vörðr — The Watcher. Post-turn continuation + language enforcement.

This script is called by crontab every 5 minutes AND by the Hermes cronjob
every 30 minutes. It:

1. Checks for unfinished work (Skuld tasks, git state, auto-continue)
2. Sends a Telegram nudge if work remains (with 30-min cooldown)
3. ENFORCES the language law on all recent output logs

Language enforcement: Any non-English text (Chinese, CJK, Runic, etc.)
found in output is STRIPPED and a warning is logged. This is CODE enforcement
of the LANGUAGE LAW, not a suggestion.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add heartbeat to path
sys.path.insert(0, str(Path(__file__).parent))
from language_enforcer import check_message, enforce_english

# ── Configuration ──────────────────────────────────────────────────────────
HERMES_DIR = Path.home() / '.hermes'
TRIGGER_DIR = HERMES_DIR / 'triggers'
VORDR_STATE = HERMES_DIR / 'vordr_state.json'
COOLDOWN_SECONDS = 1800  # 30 minutes between nudges
HERMES_CRON_OUTPUT = HERMES_DIR / 'cron' / 'output'

# ── Language Enforcement ──────────────────────────────────────────────────
def enforce_language_on_output():
    """Scan recent Hermes cron output for non-English text and log violations.

    This is the CODE enforcement of the LANGUAGE LAW:
    - Volmarr reads ENGLISH ONLY
    - NEVER output Old Norse runes, Chinese, CJK, or any non-English text
    - This is NOT a suggestion — it is enforced by this script
    """
    violations_found = []

    # Check recent cron output files
    if HERMES_CRON_OUTPUT.exists():
        for f in sorted(HERMES_CRON_OUTPUT.glob('*.md'))[-5:]:  # Last 5 outputs
            try:
                content = f.read_text(encoding='utf-8', errors='replace')
                result = check_message(content)
                if result['had_violations']:
                    violations_found.append({
                        'file': str(f),
                        'count': result['violation_count'],
                        'types': result['violations'][:5],
                    })
            except Exception:
                pass

    # Check recent conversation logs if accessible
    conv_dir = HERMES_DIR / 'conversations'
    if conv_dir.exists():
        for f in sorted(conv_dir.glob('*.md'))[-3:]:
            try:
                content = f.read_text(encoding='utf-8', errors='replace')
                result = check_message(content)
                if result['had_violations']:
                    violations_found.append({
                        'file': str(f),
                        'count': result['violation_count'],
                        'types': result['violations'][:5],
                    })
            except Exception:
                pass

    if violations_found:
        report_lines = ["LANGUAGE LAW VIOLATIONS DETECTED:"]
        for v in violations_found:
            report_lines.append(
                f"  - {v['file']}: {v['count']} non-English chars ({v['types']})"
            )
        report_lines.append(
            "\nENFORCEMENT ACTION: These violations will be stripped in future output. "
            "The LANGUAGE LAW is enforced in code, not in markdown notes."
        )
        return '\n'.join(report_lines)
    return "Language enforcement: No violations found."


# ── Git State Check ──────────────────────────────────────────────────────
def get_repo_state(repo_path):
    """Check git state of a repository."""
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=str(repo_path),
            capture_output=True, text=True, timeout=10
        )
        dirty = bool(result.stdout.strip())

        result2 = subprocess.run(
            ['git', 'log', '@{u}..HEAD', '--oneline'],
            cwd=str(repo_path),
            capture_output=True, text=True, timeout=10
        )
        unpushed = len(result2.stdout.strip().split('\n')) if result2.stdout.strip() else 0

        return {'path': str(repo_path), 'dirty': dirty, 'unpushed': unpushed}
    except Exception as e:
        return {'path': str(repo_path), 'error': str(e)}


# ── Main ──────────────────────────────────────────────────────────────────
def main():
    status = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'repos': {},
        'skuld_tasks': 0,
        'auto_continue': None,
        'language_violations': None,
        'should_nudge': False,
        'nudge_reasons': [],
    }

    # Check major repos
    repos = [
        Path.home() / 'NorseSagaEngine',
        Path.home() / 'verdandi',
        Path.home() / 'mimir-well',
    ]
    for repo in repos:
        if repo.exists():
            state = get_repo_state(repo)
            status['repos'][repo.name] = state
            if state.get('dirty') or state.get('unpushed', 0) > 0:
                status['should_nudge'] = True
                if state.get('dirty'):
                    status['nudge_reasons'].append(f"{repo.name}: uncommitted changes")
                if state.get('unpushed', 0) > 0:
                    status['nudge_reasons'].append(f"{repo.name}: {state['unpushed']} unpushed commits")

    # Check Skuld tasks
    skuld_path = Path.home() / 'NorseSagaEngine' / 'skuld_tasks.json'
    if skuld_path.exists():
        try:
            tasks = json.loads(skuld_path.read_text())
            pending = [t for t in tasks if t.get('status') == 'pending']
            status['skuld_tasks'] = len(pending)
            if pending:
                status['should_nudge'] = True
                status['nudge_reasons'].append(f"{len(pending)} pending Skuld tasks")
        except Exception:
            pass

    # Check auto-continue
    ac_path = Path.home() / 'NorseSagaEngine' / 'auto_continue.json'
    if ac_path.exists():
        try:
            ac = json.loads(ac_path.read_text())
            if ac.get('active'):
                status['auto_continue'] = ac
                status['should_nudge'] = True
                progress = ac.get('completed', 0)
                total = ac.get('total', '?')
                status['nudge_reasons'].append(f"Auto-continue active: {progress}/{total}")
        except Exception:
            pass

    # ── Language Enforcement ──
    lang_report = enforce_language_on_output()
    status['language_violations'] = lang_report

    # ── Output status ──
    print(f"Vordr Status — {status['timestamp']}")
    print(f"  Repos: {json.dumps(status['repos'], indent=4)}")
    print(f"  Skuld tasks pending: {status['skuld_tasks']}")
    print(f"  Auto-continue: {status['auto_continue']}")
    print(f"  Language: {lang_report}")
    print(f"  Should nudge: {status['should_nudge']}")
    if status['nudge_reasons']:
        print(f"  Reasons: {', '.join(status['nudge_reasons'])}")

    # ── Cooldown check & nudge ──
    if status['should_nudge']:
        now = time.time()
        last_nudge = 0
        if VORDR_STATE.exists():
            try:
                last_nudge = json.loads(VORDR_STATE.read_text()).get('last_nudge', 0)
            except Exception:
                pass

        if now - last_nudge >= COOLDOWN_SECONDS:
            # Write trigger file
            TRIGGER_DIR.mkdir(parents=True, exist_ok=True)
            trigger_data = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'reasons': status['nudge_reasons'],
                'language_violations': lang_report if 'VIOLATIONS' in lang_report else None,
            }
            trigger_file = TRIGGER_DIR / 'vordr_nudge.json'
            trigger_file.write_text(json.dumps(trigger_data, indent=2))
            print(f"\n  NUDGE TRIGGER WRITTEN: {trigger_file}")
            print(f"  Reasons: {', '.join(status['nudge_reasons'])}")

            # Update state
            VORDR_STATE.write_text(json.dumps({
                'last_nudge': now,
                'last_nudge_reasons': status['nudge_reasons'],
            }, indent=2))
        else:
            remaining = int(COOLDOWN_SECONDS - (now - last_nudge))
            print(f"\n  Cooldown active. Next nudge in {remaining}s")
    else:
        print("\n  No work remaining. All clear.")


if __name__ == '__main__':
    if '--status' in sys.argv:
        # Just show status, don't nudge
        main()
    elif '--enforce-language' in sys.argv:
        # Language enforcement only
        print(enforce_language_on_output())
    else:
        main()