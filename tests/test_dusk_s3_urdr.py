"""
Dusk slice S3 — Urðr detection lies (systemd + cron parsing).

(a) `_check_systemd` previously used `"active" in result.stdout`, which
    substring-matches `Active: inactive (dead)` -> dead services were reported
    ACTIVE and GungnirAction skipped their restart. Must parse the actual
    Active: state instead.
(b) `_check_cron` previously required `len(parts) >= 6` (5 time fields), so
    @-spec lines (@reboot, @daily, @hourly — only 2 tokens) were silently
    dropped and never counted.

Subprocess output is stubbed; these tests never touch the real system.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from heartbeat.checks.urdr import UrdrCheck

SYSTEMD_INACTIVE = """\
* runa-nervous-system.service - Runa nervous system
     Loaded: loaded (/home/pi/.config/systemd/user/runa-nervous-system.service; enabled)
     Active: inactive (dead)
"""

SYSTEMD_ACTIVE = """\
* verdandi-heartbeat.service - Verdandi heartbeat
     Loaded: loaded (/home/pi/.config/systemd/user/verdandi-heartbeat.service; enabled)
     Active: active (running) since Sat 2026-10-10 12:00:00 EDT; 4h ago
"""


def make_check():
    """Urðr check with a stub config (cron/systemd paths need no thresholds)."""
    return UrdrCheck(config=SimpleNamespace(get=lambda key, default=None: default))


def fake_run_factory(systemctl_stdout=None, crontab_stdout=""):
    """Build a fake subprocess.run that stubs systemctl and crontab."""
    systemctl_stdout = systemctl_stdout or {}

    def _fake_run(cmd, **kwargs):
        if "crontab" in cmd:
            return SimpleNamespace(
                args=cmd, returncode=0, stdout=crontab_stdout, stderr=""
            )
        if "systemctl" in cmd:
            service = cmd[-1]
            return SimpleNamespace(
                args=cmd,
                returncode=0,
                stdout=systemctl_stdout.get(service, ""),
                stderr="",
            )
        # pgrep / ps: no matches
        return SimpleNamespace(args=cmd, returncode=1, stdout="", stderr="")

    return _fake_run


def run_systemd(systemctl_stdout):
    check = make_check()
    with patch(
        "heartbeat.checks.urdr.subprocess.run",
        fake_run_factory(systemctl_stdout=systemctl_stdout),
    ):
        return check._check_systemd()


def run_cron(crontab_stdout):
    check = make_check()
    with patch(
        "heartbeat.checks.urdr.subprocess.run",
        fake_run_factory(crontab_stdout=crontab_stdout),
    ):
        return check._check_cron()


# ============================================================================
# (a) systemd Active: state parsing
# ============================================================================

class TestSystemdActiveParsing:
    def test_inactive_dead_reported_inactive(self):
        """Regression: 'Active: inactive (dead)' must NOT read as active."""
        result = run_systemd({
            "runa-nervous-system": SYSTEMD_INACTIVE,
            "verdandi-heartbeat": SYSTEMD_INACTIVE,
        })
        for svc in result.details["services"]:
            assert svc["active"] is False, (
                f"{svc['name']} wrongly reported active"
            )
        assert result.details["active_count"] == 0

    def test_active_running_reported_active(self):
        result = run_systemd({
            "runa-nervous-system": SYSTEMD_ACTIVE,
            "verdandi-heartbeat": SYSTEMD_ACTIVE,
        })
        for svc in result.details["services"]:
            assert svc["active"] is True
        assert result.details["active_count"] == 2

    def test_mixed_states(self):
        result = run_systemd({
            "runa-nervous-system": SYSTEMD_INACTIVE,   # dead
            "verdandi-heartbeat": SYSTEMD_ACTIVE,      # running
        })
        by_name = {s["name"]: s for s in result.details["services"]}
        assert by_name["runa-nervous-system"]["active"] is False
        assert by_name["verdandi-heartbeat"]["active"] is True
        assert result.details["active_count"] == 1

    def test_failed_state_is_not_active(self):
        result = run_systemd({
            "runa-nervous-system": "   Active: failed (Result: exit-code)\n",
            "verdandi-heartbeat": SYSTEMD_ACTIVE,
        })
        by_name = {s["name"]: s for s in result.details["services"]}
        assert by_name["runa-nervous-system"]["active"] is False

    @pytest.mark.parametrize("stdout", [
        "   Active: activating (start)\n",
        "   Active: deactivating (stop)\n",
        "   Active: reloading (reload)\n",
        "   Active: unknown\n",
        "",                      # no output at all
        "Loaded: loaded\n",      # no Active: line
        "active\n",              # word 'active' present but no Active: state line
    ])
    def test_non_running_outputs_are_inactive(self, stdout):
        """Only a literal 'active' Active: state counts — substring tricks fail."""
        result = run_systemd({
            "runa-nervous-system": stdout,
            "verdandi-heartbeat": stdout,
        })
        for svc in result.details["services"]:
            assert svc["active"] is False

    def test_dead_service_now_triggers_restart_eligibility(self):
        """GungnirAction restarts services with active=False; dead units must
        land there (they were previously invisible because they read active)."""
        result = run_systemd({
            "runa-nervous-system": SYSTEMD_INACTIVE,
            "verdandi-heartbeat": SYSTEMD_INACTIVE,
        })
        restartable = [
            s["name"] for s in result.details["services"] if not s.get("active")
        ]
        assert set(restartable) == {"runa-nervous-system", "verdandi-heartbeat"}


# ============================================================================
# (b) cron @-spec counting
# ============================================================================

class TestCronAtSpecs:
    def test_at_specs_counted(self):
        """Acceptance: @reboot + @daily + @hourly + one 5-field job == 4
        valid jobs (old code counted only the classic line: job_count == 1).

        NOTE: the task acceptance literally says == 3, but 3 @-specs +
        1 classic line is 4 valid job lines. Flagging to the orchestrator;
        all four lines must be counted either way.
        """
        crontab = "\n".join([
            "@reboot /home/pi/verdandi/nerve_supervise.sh start",
            "@daily /home/pi/verdandi/scripts/daily_mirror.py",
            "@hourly /home/pi/verdandi/heartbeat/pulse.sh",
            "*/5 * * * * /home/pi/verdandi/heartbeat/pulse.sh",
        ])
        result = run_cron(crontab)
        assert result.details["job_count"] == 4

    def test_at_spec_schedule_preserved(self):
        result = run_cron("@reboot /usr/bin/verdandi-boot\n")
        job = result.details["jobs"][0]
        assert job["schedule"] == "@reboot"
        assert "verdandi-boot" in job["command"]

    def test_verdandi_at_jobs_detected(self):
        """@reboot Verdandi lines must show up in verdandi_jobs."""
        crontab = "\n".join([
            "@reboot /home/pi/verdandi/heartbeat/pulse.sh",
            "@daily /usr/bin/backup-stuff",
        ])
        result = run_cron(crontab)
        assert result.details["job_count"] == 2
        assert result.details["verdandi_jobs"] == 1

    def test_comments_and_blank_lines_ignored(self):
        crontab = "\n".join([
            "# Verdandi jobs",
            "",
            "@reboot /home/pi/verdandi/boot.sh",
            "",
            "  ",
            "# another comment",
            "0 3 * * * /home/pi/verdandi/nightly.sh",
        ])
        result = run_cron(crontab)
        assert result.details["job_count"] == 2

    def test_malformed_lines_still_ignored(self):
        crontab = "\n".join([
            "@reboot",              # @-spec with no command: not a job
            "just garbage",         # no time fields
            "@hourly /bin/heartbeat",
        ])
        result = run_cron(crontab)
        assert result.details["job_count"] == 1

    def test_empty_crontab_warns(self):
        from heartbeat.checks.base import CheckSeverity
        result = run_cron("")
        assert result.details["job_count"] == 0
        assert result.severity == CheckSeverity.WARNING
