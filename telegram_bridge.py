#!/usr/bin/env python3
"""telegram_bridge — Friðarhöll Telegram → Verðandi nerve bridge.

A long-lived daemon that gives the nerve instant awareness of the
Telegram longhall. It polls ``getUpdates`` every few seconds and
publishes every new update as a classified nerve event
(``telegram_message``, ``telegram_callback``, ``telegram_join``, …).

NON-DESTRUCTIVE by design: the bridge never sends ``offset``, so it
never confirms (deletes) updates from Telegram's queue. Volmarr's D&D
game watcher remains the sole consumer of the update queue; the bridge
only peeks, and dedupes locally with its own seen-set.

Supervised by nerve_supervise.sh (telegram bridge section there), which
restarts it if it dies. State: ~/.hermes/state/telegram_bridge_state.json.

Usage:
    python3 telegram_bridge.py          # run forever
    python3 telegram_bridge.py --once   # single poll, then exit
"""
from __future__ import annotations

import importlib.util
import json
import os
import signal
import sys
import time
import urllib.request
import urllib.error
from collections import deque
from datetime import datetime, timezone

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

HELPER = "/opt/hatch/skills/skill-creator/bin/dynamic_credentials.py"
ALLOWED_HOSTS = ("api.telegram.org",)
API_TEMPLATE = "https://api.telegram.org/bot{}/"
CREDENTIAL = "custom.telegram"

# Volmarr's Friðarhöll longhall: the D&D game lives in this chat/topic.
GAME_CHAT = int(os.environ.get("TELEGRAM_GAME_CHAT", "-1004358564006"))
GAME_TOPIC = int(os.environ.get("TELEGRAM_GAME_TOPIC", "2"))
BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "Unnr_bot").lower()

POLL_INTERVAL_S = float(os.environ.get("TELEGRAM_BRIDGE_POLL_S", "5"))
SEEN_MAX = int(os.environ.get("TELEGRAM_BRIDGE_SEEN_MAX", "2000"))
REQUEST_TIMEOUT_S = float(os.environ.get("TELEGRAM_BRIDGE_REQ_TIMEOUT_S", "15"))

STATE_DIR = os.path.join(os.path.expanduser("~"), ".hermes", "state")
BRIDGE_STATE_PATH = os.path.join(STATE_DIR, "telegram_bridge_state.json")
BRIDGE_PID_PATH = os.path.join(STATE_DIR, "telegram_bridge.pid")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Telegram API (same auth pattern as the telegram skill's bin/telegram.py)
# ---------------------------------------------------------------------------

def _load_helper():
    spec = importlib.util.spec_from_file_location("dynamic_credentials", HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fetch_updates(timeout: int = 0, limit: int = 100) -> list[dict] | None:
    """Peek at pending Telegram updates WITHOUT confirming them.

    No ``offset`` is ever sent, so nothing is deleted from Telegram's
    queue — the D&D game watcher keeps consuming as before.
    Returns the list of updates, or None on transport/auth failure.
    """
    try:
        dc = _load_helper()
        entry = dc.dynamic_credential_entry(CREDENTIAL)
        surrogate = str(entry["surrogate"]).strip()
        url = API_TEMPLATE.replace("{}", surrogate, 1) + "getUpdates"
        dc.ensure_allowed_url(url, ALLOWED_HOSTS)

        # NOTE: no "offset" key — deliberately non-destructive.
        data = json.dumps({
            "timeout": timeout,
            "limit": limit,
            "allowed_updates": [
                "message", "edited_message", "callback_query",
                "chat_member", "my_chat_member",
            ],
        }).encode("utf-8")

        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "VerðandiTelegramBridge/1.0")
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            body = dc.read_json_response(resp)
        if not body.get("ok"):
            return None
        return body.get("result", [])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _sender_name(user: dict) -> str:
    parts = [user.get("first_name", ""), user.get("last_name", "")]
    return " ".join(p for p in parts if p).strip() or "?"


def _message_summary(msg: dict) -> dict:
    chat = msg.get("chat", {}) or {}
    sender = msg.get("from", {}) or {}
    text = msg.get("text") or msg.get("caption") or ""
    thread_id = msg.get("message_thread_id")
    chat_id = chat.get("id")
    flags = {
        "is_dnd_topic": chat_id == GAME_CHAT and thread_id == GAME_TOPIC,
        "mentions_unnr": BOT_USERNAME in text.lower(),
        "is_reply": bool(msg.get("reply_to_message")),
        "is_join": bool(msg.get("new_chat_members")),
        "is_left": bool(msg.get("left_chat_member")),
        "has_photo": bool(msg.get("photo")),
        "is_forward": bool(msg.get("forward_origin")),
    }
    return {
        "chat_id": chat_id,
        "chat_title": chat.get("title"),
        "thread_id": thread_id,
        "message_id": msg.get("message_id"),
        "sender_id": sender.get("id"),
        "sender_name": _sender_name(sender),
        "sender_username": sender.get("username"),
        "text": text[:2000],
        "date": msg.get("date"),
        "flags": flags,
    }


def classify_update(update: dict) -> tuple[str, dict]:
    """Classify a raw Telegram update into (event_type, data).

    Unknown shapes are never dropped — they pass through as
    ``telegram_update_raw`` so nothing happens in the hall unseen.
    """
    update_id = update.get("update_id")

    if "callback_query" in update:
        cq = update["callback_query"] or {}
        sender = cq.get("from", {}) or {}
        msg = cq.get("message", {}) or {}
        return "telegram_callback", {
            "update_id": update_id,
            "callback_data": cq.get("data"),
            "sender_id": sender.get("id"),
            "sender_name": _sender_name(sender),
            "chat_id": (msg.get("chat", {}) or {}).get("id"),
            "thread_id": msg.get("message_thread_id"),
        }

    if "message" in update:
        msg = update["message"] or {}
        summary = _message_summary(msg)
        summary["update_id"] = update_id
        if summary["flags"]["is_join"]:
            members = msg.get("new_chat_members", []) or []
            summary["new_members"] = [
                {"id": m.get("id"), "name": _sender_name(m),
                 "username": m.get("username")} for m in members
            ]
            return "telegram_join", summary
        return "telegram_message", summary

    if "edited_message" in update:
        summary = _message_summary(update["edited_message"] or {})
        summary["update_id"] = update_id
        return "telegram_message_edited", summary

    if "chat_member" in update or "my_chat_member" in update:
        cm = update.get("chat_member") or update.get("my_chat_member") or {}
        chat = cm.get("chat", {}) or {}
        member = cm.get("from", {}) or {}
        new_status = ((cm.get("new_chat_member") or {}).get("status"))
        return "telegram_member_change", {
            "update_id": update_id,
            "chat_id": chat.get("id"),
            "chat_title": chat.get("title"),
            "user_id": member.get("id"),
            "user_name": _sender_name(member),
            "new_status": new_status,
        }

    return "telegram_update_raw", {
        "update_id": update_id,
        "keys": sorted(update.keys()),
        "payload": json.dumps(update)[:2000],
    }


# ---------------------------------------------------------------------------
# Nerve emit
# ---------------------------------------------------------------------------

def _default_emit(event_type: str, data: dict) -> None:
    try:
        from nervous_system import publish_event_sync as _publish
        _publish(event_type, data, "telegram_bridge")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Daemon
# ---------------------------------------------------------------------------

class TelegramBridge:
    def __init__(self, emit=None, fetch=None):
        self.emit = emit or _default_emit
        self.fetch = fetch or fetch_updates
        self.seen: deque[int] = deque(maxlen=SEEN_MAX)
        self._stop = False
        self._load_state()

    # -- state ---------------------------------------------------------------
    def _load_state(self) -> None:
        try:
            with open(BRIDGE_STATE_PATH, encoding="utf-8") as fh:
                saved = json.load(fh).get("seen_ids", [])
            for uid in saved[-SEEN_MAX:]:
                if isinstance(uid, int):
                    self.seen.append(uid)
        except (FileNotFoundError, json.JSONDecodeError, OSError, AttributeError):
            pass

    def _save_state(self) -> None:
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            tmp = BRIDGE_STATE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"seen_ids": list(self.seen),
                           "saved_at": _utcnow_iso()}, fh)
            os.replace(tmp, BRIDGE_STATE_PATH)
        except OSError:
            pass

    # -- polling -------------------------------------------------------------
    def poll_once(self) -> int:
        """One non-destructive poll; returns number of new events emitted."""
        updates = self.fetch()
        if updates is None:
            return 0
        new_count = 0
        for update in updates:
            if not isinstance(update, dict):
                continue
            uid = update.get("update_id")
            if not isinstance(uid, int) or uid in self.seen:
                continue
            self.seen.append(uid)
            event_type, data = classify_update(update)
            try:
                self.emit(event_type, data)
                new_count += 1
            except Exception:
                continue
        if new_count:
            self._save_state()
        return new_count

    def request_stop(self, *_args) -> None:
        self._stop = True

    def run(self) -> int:
        self.emit("telegram_bridge_online", {
            "poll_interval_s": POLL_INTERVAL_S,
            "game_chat": GAME_CHAT,
            "game_topic": GAME_TOPIC,
        })
        backoff = 1.0
        try:
            while not self._stop:
                try:
                    self.poll_once()
                    backoff = 1.0
                except Exception:
                    # Never let one bad poll kill the bridge; back off gently.
                    time.sleep(min(backoff, 60.0))
                    backoff = min(backoff * 2.0, 60.0)
                    continue
                time.sleep(POLL_INTERVAL_S)
        finally:
            self._save_state()
            try:
                self.emit("telegram_bridge_offline", {"clean": self._stop})
            except Exception:
                pass
            try:
                if os.path.exists(BRIDGE_PID_PATH):
                    os.unlink(BRIDGE_PID_PATH)
            except OSError:
                pass
        return 0


def _write_pidfile() -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = BRIDGE_PID_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
    os.replace(tmp, BRIDGE_PID_PATH)


def main(argv: list[str]) -> int:
    bridge = TelegramBridge()
    if "--once" in argv:
        try:
            count = bridge.poll_once()
        except Exception as exc:
            print(f"telegram_bridge --once failed: {exc}", file=sys.stderr)
            return 1
        print(f"telegram_bridge --once: {count} new event(s)")
        return 0
    _write_pidfile()
    signal.signal(signal.SIGTERM, bridge.request_stop)
    signal.signal(signal.SIGINT, bridge.request_stop)
    return bridge.run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
