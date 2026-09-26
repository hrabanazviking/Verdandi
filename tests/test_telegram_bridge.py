"""Tests for telegram_bridge.py — the Friðarhöll → nerve bridge.

Verifies classification of hall updates, the non-destructive peek
guarantee (no ``offset`` ever sent), local dedupe, and state roundtrip.
"""
import json
import sys

import pytest

sys.path.insert(0, "/home/hatch/workspace/repos/Verdandi")

import telegram_bridge as tb
from telegram_bridge import TelegramBridge, classify_update


GAME_CHAT = tb.GAME_CHAT
GAME_TOPIC = tb.GAME_TOPIC


def _msg(uid, text, thread=2, sender="Volmarr"):
    return {
        "update_id": uid,
        "message": {
            "message_id": uid + 1000,
            "message_thread_id": thread,
            "date": 1780000000,
            "chat": {"id": GAME_CHAT, "title": "Friðarhöll"},
            "from": {"id": 42, "first_name": sender, "username": "volmarr"},
            "text": text,
        },
    }


def _make_bridge(updates, state_dir, monkeypatch):
    """Bridge with a fake fetch (peek) and a recording emit."""
    emitted = []

    def fake_fetch():
        return updates

    monkeypatch.setattr(tb, "BRIDGE_STATE_PATH",
                        str(state_dir / "telegram_bridge_state.json"))
    monkeypatch.setattr(tb, "BRIDGE_PID_PATH",
                        str(state_dir / "telegram_bridge.pid"))
    bridge = TelegramBridge(emit=lambda t, d: emitted.append((t, d)),
                            fetch=fake_fetch)
    return bridge, emitted


# --- classification --------------------------------------------------------

def test_dnd_topic_message_classified_with_flags():
    etype, data = classify_update(_msg(1, "I draw my seax."))
    assert etype == "telegram_message"
    assert data["flags"]["is_dnd_topic"] is True
    assert data["chat_id"] == GAME_CHAT
    assert data["thread_id"] == GAME_TOPIC
    assert data["sender_name"] == "Volmarr"
    assert data["text"] == "I draw my seax."


def test_mention_of_unnr_flagged():
    etype, data = classify_update(_msg(2, "hey @Unnr_bot what do you think"))
    assert etype == "telegram_message"
    assert data["flags"]["mentions_unnr"] is True


def test_join_becomes_telegram_join():
    update = _msg(3, "")
    update["message"]["new_chat_members"] = [
        {"id": 99, "first_name": "Astrid", "username": "astrid_v"}
    ]
    etype, data = classify_update(update)
    assert etype == "telegram_join"
    assert data["new_members"][0]["name"] == "Astrid"
    assert data["flags"]["is_join"] is True


def test_callback_query_classified():
    update = {"update_id": 4, "callback_query": {
        "id": "cq1", "data": "roll_d20",
        "from": {"id": 42, "first_name": "Volmarr"},
        "message": {"message_id": 5,
                    "chat": {"id": GAME_CHAT},
                    "message_thread_id": GAME_TOPIC},
    }}
    etype, data = classify_update(update)
    assert etype == "telegram_callback"
    assert data["callback_data"] == "roll_d20"
    assert data["sender_name"] == "Volmarr"


def test_edited_message_classified():
    update = {"update_id": 5, "edited_message": {
        "message_id": 6, "date": 1780000001,
        "chat": {"id": GAME_CHAT, "title": "Friðarhöll"},
        "from": {"id": 42, "first_name": "Volmarr"},
        "text": "corrected move",
    }}
    etype, data = classify_update(update)
    assert etype == "telegram_message_edited"
    assert data["text"] == "corrected move"


def test_member_change_classified():
    update = {"update_id": 6, "chat_member": {
        "chat": {"id": GAME_CHAT, "title": "Friðarhöll"},
        "from": {"id": 7, "first_name": "Skald"},
        "new_chat_member": {"status": "member"},
    }}
    etype, data = classify_update(update)
    assert etype == "telegram_member_change"
    assert data["new_status"] == "member"


def test_unknown_shape_passes_through_raw():
    update = {"update_id": 7, "mystery_field": {"deep": True}}
    etype, data = classify_update(update)
    assert etype == "telegram_update_raw"
    assert data["update_id"] == 7


# --- non-destructive peek guarantee -----------------------------------------

def test_fetch_never_sends_offset(monkeypatch):
    """The bridge must never consume the queue the game watcher owns."""
    sent_payloads = []

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None):
        sent_payloads.append(json.loads(req.data.decode("utf-8")))
        raise RuntimeError("stop before network")

    class FakeDC:
        @staticmethod
        def dynamic_credential_entry(name):
            return {"surrogate": "hsurr:test"}
        @staticmethod
        def ensure_allowed_url(url, hosts): pass
        @staticmethod
        def read_json_response(resp): return {"ok": True, "result": []}

    monkeypatch.setattr(tb, "_load_helper", lambda: FakeDC)
    import urllib.request as urlreq
    monkeypatch.setattr(urlreq, "urlopen", fake_urlopen)

    assert tb.fetch_updates() is None  # transport failed by design
    assert len(sent_payloads) == 1
    assert "offset" not in sent_payloads[0]
    assert sent_payloads[0]["timeout"] == 0  # no long-poll hang in this env


# --- dedupe & state -----------------------------------------------------------

def test_poll_once_dedupes_repeated_updates(tmp_path, monkeypatch):
    updates = [_msg(10, "first"), _msg(11, "second")]
    bridge, emitted = _make_bridge(updates, tmp_path, monkeypatch)
    assert bridge.poll_once() == 2
    assert bridge.poll_once() == 0  # same batch seen again: silent
    assert len(emitted) == 2


def test_state_roundtrip(tmp_path, monkeypatch):
    updates = [_msg(20, "hello")]
    bridge, _ = _make_bridge(updates, tmp_path, monkeypatch)
    bridge.poll_once()

    # A fresh bridge on the same state dir must not re-emit.
    bridge2, emitted2 = _make_bridge(updates, tmp_path, monkeypatch)
    assert bridge2.poll_once() == 0
    assert emitted2 == []


def test_fetch_failure_is_silent_and_retried(tmp_path, monkeypatch):
    def failing_fetch():
        return None
    monkeypatch.setattr(tb, "BRIDGE_STATE_PATH",
                        str(tmp_path / "telegram_bridge_state.json"))
    monkeypatch.setattr(tb, "BRIDGE_PID_PATH",
                        str(tmp_path / "telegram_bridge.pid"))
    emitted = []
    bridge = TelegramBridge(emit=lambda t, d: emitted.append((t, d)),
                            fetch=failing_fetch)
    assert bridge.poll_once() == 0
    assert emitted == []
