"""
Verðandi Heartbeat — The Pulse of Becoming.

A self-aware heartbeat daemon for AI agents. Monitors health, projects,
memory, and schedule — reacting to what it finds. Not passive monitoring.
Active self-care.

Designed for Hermes Agent, adaptable to any AI agent. File-location-agnostic.
Best on Raspberry Pi, works on all Linux, macOS, iOS, and WSL.

This is Wave 1 — The Skeleton. The bones upon which flesh will grow.
"""

__version__ = "0.2.0"
__norse_name__ = "Verðandi Hjartsláttur"
__description__ = "The heartbeat of becoming — AGI-focused self-awareness daemon"

from heartbeat.paths import (
    get_state_dir,
    get_config_dir,
    get_log_dir,
    get_pid_dir,
    get_socket_path,
    get_config_path,
    get_db_path,
    get_pid_path,
    get_log_path,
    resolve_path,
)

__all__ = [
    "get_state_dir",
    "get_config_dir",
    "get_log_dir",
    "get_pid_dir",
    "get_socket_path",
    "get_config_path",
    "get_db_path",
    "get_pid_path",
    "get_log_path",
    "resolve_path",
]