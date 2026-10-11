"""Dawn forge 2026-10-11: slices 3, 4, 5 (nervous_system.py).

S3: a single frame bigger than the reader limit must get the structured
    {"nerve_type":"error","reason":"message_too_large"} frame — no
    traceback, hub keeps serving.
S4: a quiet subscriber (pure listener) must NOT be disconnected after
    SUBSCRIBER_TIMEOUT_S — the hub proves liveness with a keepalive ping.
S5: cmd_stop's SIGTERM must run the graceful shutdown path: subscribers
    get the {"nerve_type":"shutdown"} frame and the log shows the drain.
"""
import asyncio
import json
import os
import signal
import subprocess
import sys
import time

import pytest

import nervous_system as ns

REPO = str(__import__("pathlib").Path(__file__).resolve().parent.parent)


@pytest.fixture()
def iso(tmp_path, monkeypatch):
    state_dir = tmp_path / ".hermes" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    orig = {k: getattr(ns, k) for k in ("STATE_DIR", "SOCKET_PATH", "FEED_PATH", "PID_PATH", "LOG_PATH")}
    ns.STATE_DIR = state_dir
    ns.SOCKET_PATH = state_dir / "test_runa.sock"
    ns.FEED_PATH = state_dir / "nerve_feed.jsonl"
    ns.PID_PATH = state_dir / "nervous_system.pid"
    ns.LOG_PATH = state_dir / "nervous_system.log"
    yield state_dir
    for k, v in orig.items():
        setattr(ns, k, v)


def _run(coro):
    return asyncio.run(coro)


# --- S3 -------------------------------------------------------------------
def test_oversized_newlineless_frame_gets_structured_error(iso):
    async def _body():
        hub = ns.NerveHub()
        task = asyncio.create_task(hub.serve())
        try:
            for _ in range(100):
                await asyncio.sleep(0.05)
                if ns.SOCKET_PATH.exists():
                    break
            assert ns.SOCKET_PATH.exists()
            reader, writer = await asyncio.open_unix_connection(str(ns.SOCKET_PATH))
            # 2 MiB, no newline: exceeds the reader limit (MAX+4096)
            writer.write(b"x" * (2 * 1024 * 1024))
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout=10)
            assert line, "hub must answer with a structured error frame, not RST"
            frame = json.loads(line.decode())
            assert frame.get("nerve_type") == "error"
            assert frame.get("reason") == "message_too_large"
            writer.close()
            # hub must still be serving
            r2, w2 = await asyncio.open_unix_connection(str(ns.SOCKET_PATH))
            w2.write(json.dumps({"nerve_type": "ping"}).encode() + b"\n")
            await w2.drain()
            pong = await asyncio.wait_for(r2.readline(), timeout=10)
            assert json.loads(pong.decode()).get("nerve_type") == "pong"
            w2.close()
        finally:
            hub._shutdown_event.set()
            await asyncio.wait_for(task, timeout=10)
    _run(_body())


# --- S4 -------------------------------------------------------------------
def test_quiet_subscriber_survives_timeout_with_keepalive(iso, monkeypatch):
    monkeypatch.setattr(ns, "SUBSCRIBER_TIMEOUT_S", 2)

    async def _body():
        hub = ns.NerveHub()
        task = asyncio.create_task(hub.serve())
        try:
            for _ in range(100):
                await asyncio.sleep(0.05)
                if ns.SOCKET_PATH.exists():
                    break
            reader, writer = await asyncio.open_unix_connection(str(ns.SOCKET_PATH))
            writer.write(json.dumps({"nerve_type": "subscribe"}).encode() + b"\n")
            await writer.drain()
            # stay silent for >2x the timeout; expect keepalive pings, no EOF
            got_ping = False
            deadline = time.time() + 8
            while time.time() < deadline:
                line = await asyncio.wait_for(reader.readline(), timeout=9)
                assert line, "quiet subscriber was disconnected (EOF)"
                frame = json.loads(line.decode())
                if frame.get("nerve_type") == "ping":
                    got_ping = True
                    break
            assert got_ping, "no keepalive ping received within the window"
            writer.close()
        finally:
            hub._shutdown_event.set()
            await asyncio.wait_for(task, timeout=10)
    _run(_body())


# --- S5 -------------------------------------------------------------------
def test_sigterm_triggers_graceful_shutdown(iso, tmp_path):
    fake_home = tmp_path / "home"
    (fake_home / ".hermes" / "state").mkdir(parents=True)
    env = dict(os.environ, HOME=str(fake_home))
    proc = subprocess.Popen(
        [sys.executable, "nervous_system.py", "serve"],
        cwd=REPO, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        sock = fake_home / ".hermes" / "state" / "runa.sock"
        for _ in range(100):
            time.sleep(0.1)
            if sock.exists():
                break
        assert sock.exists(), "hub did not start"

        import socket as sock_mod
        s = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
        s.settimeout(10)
        s.connect(str(sock))
        f = s.makefile("r")
        s.sendall(json.dumps({"nerve_type": "subscribe"}).encode() + b"\n")
        # consume the 'subscribed' ack
        f.readline()

        proc.send_signal(signal.SIGTERM)
        # the subscriber must receive the documented shutdown frame
        frames = []
        deadline = time.time() + 15
        while time.time() < deadline:
            line = f.readline()
            if not line:
                break
            frames.append(json.loads(line))
            if any(fr.get("nerve_type") == "shutdown" for fr in frames):
                break
        assert any(fr.get("nerve_type") == "shutdown" for fr in frames), (
            f"no shutdown frame received; got: {frames}")
        proc.wait(timeout=15)
        log_file = fake_home / ".hermes" / "state" / "nervous_system.log"
        log_text = log_file.read_text() if log_file.exists() else ""
        assert "Draining subscribers" in log_text, (
            f"no graceful drain in hub log:\n{log_text[-2000:]}")
    finally:
        if proc.poll() is None:
            proc.kill()
        s.close()
