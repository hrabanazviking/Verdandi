"""Tests for telegram_bridge.py — the Friðarhöll → nerve bridge.

Verifies classification of hall updates, the non-destructive peek
guarantee (no ``offset`` ever sent), local dedupe, and state roundtrip.
"""
import json
import sys
import time

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


def _no_sleep(monkeypatch):
    """Slice 14 retries sleep between attempts; patch to keep tests fast."""
    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)


def test_fetch_failure_retries_then_emits_event(tmp_path, monkeypatch):
    """Slice 14: a dead fetch never raises — the transport is retried
    inside the poll (bounded), then exactly one failure event is emitted
    to the nerve for that poll (replaces the old silent-failure test)."""
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    def failing_fetch():
        calls["n"] += 1
        return None

    monkeypatch.setattr(tb, "BRIDGE_STATE_PATH",
                        str(tmp_path / "telegram_bridge_state.json"))
    monkeypatch.setattr(tb, "BRIDGE_PID_PATH",
                        str(tmp_path / "telegram_bridge.pid"))
    emitted = []
    bridge = TelegramBridge(emit=lambda t, d: emitted.append((t, d)),
                            fetch=failing_fetch)
    assert bridge.poll_once() == 0
    assert calls["n"] == tb.SEND_MAX_RETRIES + 1  # retried, bounded
    assert bridge.consecutive_fetch_failures == 1  # one poll = one count
    failures = [d for t, d in emitted
                if t == "telegram_bridge_transport_failed"]
    assert len(failures) == 1
    assert failures[0]["consecutive_failures"] == 1
    assert failures[0]["last_error"] == "transport returned None"


def test_fetch_failures_are_counted_not_silent(tmp_path, monkeypatch):
    """Regression 2026-09-26: a custom User-Agent made Telegram drop every
    poll (RemoteDisconnected); fetch returned None and poll_once() == 0
    masked it for ~45 minutes. Failures must now be counted."""
    _no_sleep(monkeypatch)

    def failing_fetch():
        return None
    monkeypatch.setattr(tb, "BRIDGE_STATE_PATH",
                        str(tmp_path / "telegram_bridge_state.json"))
    monkeypatch.setattr(tb, "BRIDGE_PID_PATH",
                        str(tmp_path / "telegram_bridge.pid"))
    bridge = TelegramBridge(emit=lambda t, d: None, fetch=failing_fetch)
    assert bridge.poll_once() == 0
    assert bridge.consecutive_fetch_failures == 1
    assert bridge.poll_once() == 0
    assert bridge.consecutive_fetch_failures == 2
    # A successful (empty) poll resets the streak.
    bridge.fetch = lambda: []
    assert bridge.poll_once() == 0
    assert bridge.consecutive_fetch_failures == 0


# --- bounded retry with exponential backoff + jitter (slice 14) ---------------

def test_retry_recovers_after_transient_fetch_failures(tmp_path, monkeypatch):
    """(a) fake fetch failing twice then succeeding → poll succeeds."""
    _no_sleep(monkeypatch)
    calls = {"n": 0}
    updates = [_msg(30, "back online")]

    def flaky_fetch():
        calls["n"] += 1
        if calls["n"] <= 2:
            return None
        return updates

    monkeypatch.setattr(tb, "BRIDGE_STATE_PATH",
                        str(tmp_path / "telegram_bridge_state.json"))
    monkeypatch.setattr(tb, "BRIDGE_PID_PATH",
                        str(tmp_path / "telegram_bridge.pid"))
    emitted = []
    bridge = TelegramBridge(emit=lambda t, d: emitted.append((t, d)),
                            fetch=flaky_fetch)
    assert bridge.poll_once() == 1
    assert calls["n"] == 3  # two failed attempts, then success
    assert bridge.consecutive_fetch_failures == 0
    assert all(t != "telegram_bridge_transport_failed" for t, _ in emitted)


def test_retry_treats_exceptions_as_failures(monkeypatch):
    """A raising transport is retried and its error recorded."""
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("reset by peer")
        return {"ok": True}

    value, last_error = tb._request_with_retry(flaky)
    assert value == {"ok": True}
    assert last_error is None
    assert calls["n"] == 2


def test_exhausted_retries_emit_failure_event_once_per_poll(tmp_path, monkeypatch):
    """(b) fake fetch always failing → after retries are exhausted a
    failure event is emitted to the nerve, and the counter increments
    once per poll, not per retry."""
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    def failing_fetch():
        calls["n"] += 1
        return None

    monkeypatch.setattr(tb, "BRIDGE_STATE_PATH",
                        str(tmp_path / "telegram_bridge_state.json"))
    monkeypatch.setattr(tb, "BRIDGE_PID_PATH",
                        str(tmp_path / "telegram_bridge.pid"))
    emitted = []
    bridge = TelegramBridge(emit=lambda t, d: emitted.append((t, d)),
                            fetch=failing_fetch)
    assert bridge.poll_once() == 0
    assert bridge.poll_once() == 0
    assert calls["n"] == 2 * (tb.SEND_MAX_RETRIES + 1)
    assert bridge.consecutive_fetch_failures == 2  # one count per poll
    failures = [d for t, d in emitted
                if t == "telegram_bridge_transport_failed"]
    assert len(failures) == 2  # one event per exhausted poll
    assert failures[0]["consecutive_failures"] == 1
    assert failures[1]["consecutive_failures"] == 2
    assert isinstance(failures[1]["last_error"], str)


def test_retry_backoff_is_bounded_exponential(monkeypatch):
    """Delays grow as base*2**attempt plus jitter, capped at the cap."""
    delays = []
    monkeypatch.setattr(time, "sleep", lambda s: delays.append(s))
    monkeypatch.setattr(tb.random, "uniform", lambda a, b: 0.0)
    monkeypatch.setattr(tb, "SEND_MAX_RETRIES", 3)
    monkeypatch.setattr(tb, "SEND_BACKOFF_BASE_S", 1.0)
    monkeypatch.setattr(tb, "SEND_BACKOFF_CAP_S", 60.0)
    value, _ = tb._request_with_retry(lambda: None)
    assert value is None
    assert delays == [1.0, 2.0, 4.0]


def test_retry_backoff_never_exceeds_cap(monkeypatch):
    delays = []
    monkeypatch.setattr(time, "sleep", lambda s: delays.append(s))
    monkeypatch.setattr(tb.random, "uniform", lambda a, b: 5.0)
    monkeypatch.setattr(tb, "SEND_MAX_RETRIES", 3)
    monkeypatch.setattr(tb, "SEND_BACKOFF_BASE_S", 40.0)
    monkeypatch.setattr(tb, "SEND_BACKOFF_CAP_S", 60.0)
    tb._request_with_retry(lambda: None)
    assert delays == [45.0, 60.0, 60.0]  # 40, 80+5, 160+5 → capped


def _fake_dc(monkeypatch, reply):
    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class FakeDC:
        @staticmethod
        def dynamic_credential_entry(name):
            assert name == tb.CREDENTIAL
            return {"surrogate": "hsurr:test"}

        @staticmethod
        def ensure_allowed_url(url, hosts):
            assert hosts == tb.ALLOWED_HOSTS
            assert "api.telegram.org" in url

        @staticmethod
        def read_json_response(resp):
            return reply

    monkeypatch.setattr(tb, "_load_helper", lambda: FakeDC)
    import urllib.request as urlreq
    return FakeResp, urlreq


def test_send_message_retries_then_succeeds(monkeypatch):
    """(c) fake send transport failing twice then succeeding → sent."""
    _no_sleep(monkeypatch)
    attempts = {"n": 0}
    urls = []

    FakeResp, urlreq = _fake_dc(monkeypatch, {"ok": True,
                                              "result": {"message_id": 7}})

    def fake_urlopen(req, timeout=None):
        attempts["n"] += 1
        urls.append(req.full_url)
        if attempts["n"] <= 2:
            raise RuntimeError("boom")
        return FakeResp()

    monkeypatch.setattr(urlreq, "urlopen", fake_urlopen)
    result = tb.send_message(-123, "hello hall")
    assert result == {"ok": True, "result": {"message_id": 7}}
    assert attempts["n"] == 3
    assert urls[-1].endswith("/sendMessage")


def test_send_message_gives_up_after_retries(monkeypatch):
    """An always-dead send transport returns None after the bounded
    attempts — no exception escapes."""
    _no_sleep(monkeypatch)
    attempts = {"n": 0}
    FakeResp, urlreq = _fake_dc(monkeypatch, {"ok": True, "result": {}})

    def always_fail(req, timeout=None):
        attempts["n"] += 1
        raise RuntimeError("down")

    monkeypatch.setattr(urlreq, "urlopen", always_fail)
    assert tb.send_message(-123, "x") is None
    assert attempts["n"] == tb.SEND_MAX_RETRIES + 1


# --- truncation to Telegram's 4096-char limit (slice 15) ------------------------

def test_long_message_truncated_with_marker():
    text = "x" * 5000
    out = tb._truncate_for_telegram(text)
    assert len(out) == tb.TELEGRAM_MESSAGE_LIMIT  # exactly 4096
    assert out.endswith(tb.TRUNCATION_MARKER)
    assert out.startswith("x" * (tb.TELEGRAM_MESSAGE_LIMIT -
                                 len(tb.TRUNCATION_MARKER)))


def test_short_message_passes_through_unchanged():
    assert tb._truncate_for_telegram("short hall note") == "short hall note"
    exact = "y" * tb.TELEGRAM_MESSAGE_LIMIT
    assert tb._truncate_for_telegram(exact) == exact


def test_send_message_posts_truncated_body(monkeypatch):
    """send_message truncates a 5000-char text before posting (slice 15
    wired into the outbound path)."""
    _no_sleep(monkeypatch)
    sent = []

    FakeResp, urlreq = _fake_dc(monkeypatch, {"ok": True, "result": {}})

    def fake_urlopen(req, timeout=None):
        sent.append(json.loads(req.data.decode("utf-8")))
        return FakeResp()

    monkeypatch.setattr(urlreq, "urlopen", fake_urlopen)
    tb.send_message(-123, "z" * 5000)
    body = sent[0]["text"]
    assert len(body) <= 4096
    assert body.endswith(tb.TRUNCATION_MARKER)
    assert sent[0]["chat_id"] == -123
