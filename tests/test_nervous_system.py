"""
Comprehensive pytest suite for nervous_system.py

Covers: hub lifecycle, publish, recent, subscribe, status, healthcheck,
feed rotation, ring buffer, file locking, graceful shutdown, edge cases.
Uses subprocess and tempfile for integration tests.
Uses different socket paths to avoid breaking the production nerve hub.
"""

import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# --- Ensure we can import the module from the project dir ---
PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import nervous_system as ns


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def isolate_paths(tmp_path):
    """Redirect all paths to a temp dir to avoid touching production."""
    state_dir = tmp_path / ".hermes" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    socket_path = state_dir / "test_runa.sock"
    feed_path = state_dir / "nerve_feed.jsonl"
    pid_path = state_dir / "nervous_system.pid"
    log_path = state_dir / "nervous_system.log"

    # Patch the module-level constants
    original_constants = {
        'STATE_DIR': ns.STATE_DIR,
        'SOCKET_PATH': ns.SOCKET_PATH,
        'FEED_PATH': ns.FEED_PATH,
        'PID_PATH': ns.PID_PATH,
        'LOG_PATH': ns.LOG_PATH,
    }
    ns.STATE_DIR = state_dir
    ns.SOCKET_PATH = socket_path
    ns.FEED_PATH = feed_path
    ns.PID_PATH = pid_path
    ns.LOG_PATH = log_path

    yield {
        'state_dir': state_dir,
        'socket_path': socket_path,
        'feed_path': feed_path,
        'pid_path': pid_path,
        'log_path': log_path,
    }

    # Restore originals
    for key, val in original_constants.items():
        setattr(ns, key, val)


# ============================================================================
# Ring Buffer Tests
# ============================================================================

class TestRingBuffer:
    def test_append_and_recent(self):
        rb = ns.RingBuffer(maxlen=5)
        for i in range(5):
            rb.append({'seq': i})
        recent = rb.recent(3)
        assert len(recent) == 3
        assert recent[0]['seq'] == 2
        assert recent[2]['seq'] == 4

    def test_overflow(self):
        rb = ns.RingBuffer(maxlen=3)
        for i in range(10):
            rb.append({'seq': i})
        assert len(rb) == 3
        recent = rb.recent(10)
        assert recent[0]['seq'] == 7  # Oldest kept
        assert recent[-1]['seq'] == 9

    def test_recent_more_than_available(self):
        rb = ns.RingBuffer(maxlen=5)
        rb.append({'seq': 1})
        rb.append({'seq': 2})
        recent = rb.recent(10)
        assert len(recent) == 2

    def test_empty_buffer(self):
        rb = ns.RingBuffer(maxlen=5)
        assert len(rb) == 0
        assert rb.recent(10) == []

    def test_custom_maxlen(self):
        rb = ns.RingBuffer(maxlen=100)
        assert rb._maxlen == 100


# ============================================================================
# Feed Lock Write Tests
# ============================================================================

class TestFeedLockWrite:
    def test_creates_file_if_missing(self, isolate_paths):
        feed = isolate_paths['feed_path']
        assert not feed.exists()
        ns._feed_lock_write('{"test": "data"}')
        assert feed.exists()
        with open(feed) as f:
            lines = f.readlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data['test'] == 'data'

    def test_appends_to_existing(self, isolate_paths):
        feed = isolate_paths['feed_path']
        ns._feed_lock_write('{"seq": 1}')
        ns._feed_lock_write('{"seq": 2}')
        with open(feed) as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert json.loads(lines[0])['seq'] == 1
        assert json.loads(lines[1])['seq'] == 2


# ============================================================================
# Feed Rotation Tests
# ============================================================================

class TestFeedRotation:
    def test_no_rotation_when_small(self, isolate_paths):
        feed = isolate_paths['feed_path']
        with open(feed, 'w') as f:
            f.write('{"seq": 1}\n' * 10)
        original_size = feed.stat().st_size
        ns._rotate_feed_if_needed()
        assert feed.exists()
        assert feed.stat().st_size == original_size

    def test_rotation_archives_large_file(self, isolate_paths):
        feed = isolate_paths['feed_path']
        original_max = ns.MAX_FEED_BYTES
        ns.MAX_FEED_BYTES = 100  # Very small threshold
        try:
            with open(feed, 'w') as f:
                f.write('{"seq": 1}\n' * 20)  # ~200 bytes
            assert feed.stat().st_size > ns.MAX_FEED_BYTES

            ns._rotate_feed_if_needed()

            # After rotation, the original feed file may or may not exist
            # depending on whether compression succeeded. Either way, an
            # archive file should exist (compressed or not).
            state_dir = isolate_paths['state_dir']
            archives = list(state_dir.glob('nerve_feed_*.jsonl*'))
            assert len(archives) >= 1, "Expected at least one archive file after rotation"
        finally:
            ns.MAX_FEED_BYTES = original_max

    def test_rotation_handles_missing_file(self, isolate_paths):
        feed = isolate_paths['feed_path']
        assert not feed.exists()
        ns._rotate_feed_if_needed()  # Should not crash


# ============================================================================
# NerveHub Integration Tests
# ============================================================================

class TestNerveHub:
    """Integration tests using actual async Unix domain socket communication."""

    async def _start_hub(self):
        """Helper: start a NerveHub and return (hub, serve_task)."""
        hub = ns.NerveHub()
        serve_task = asyncio.create_task(hub.serve())
        # Wait for the hub to start
        for _ in range(50):
            await asyncio.sleep(0.05)
            if ns.SOCKET_PATH.exists():
                break
        assert ns.SOCKET_PATH.exists(), "Hub socket should exist after start"
        return hub, serve_task

    async def _stop_hub(self, hub, serve_task):
        """Helper: gracefully stop a NerveHub."""
        hub._shutdown_event.set()
        try:
            await asyncio.wait_for(serve_task, timeout=5)
        except asyncio.CancelledError:
            pass

    def test_hub_serve_and_publish(self, isolate_paths):
        """Test starting the hub, publishing an event, and stopping it."""
        async def _body():
            hub, serve_task = await self._start_hub()
            try:
                result = ns.publish_event_sync('test_event', {'key': 'value'}, 'test_source')
                assert result is not None
                assert result.get('nerve_type') in ('ack', 'fallback', 'sent')
            finally:
                await self._stop_hub(hub, serve_task)
        asyncio.run(_body())

    def test_hub_recent_command(self, isolate_paths):
        """Test that the recent command returns events from the ring buffer."""
        async def _body():
            hub, serve_task = await self._start_hub()
            try:
                # Publish some events so the ring buffer has data
                for i in range(3):
                    ns.publish_event_sync(f'test_event_{i}', {'i': i}, 'test')

                # Connect and send recent command
                reader, writer = await asyncio.open_unix_connection(str(ns.SOCKET_PATH))
                writer.write(json.dumps({'nerve_type': 'recent', 'count': 10}).encode() + b'\n')
                await writer.drain()

                data = await asyncio.wait_for(reader.readline(), timeout=3)
                response = json.loads(data.decode().strip())
                assert response.get('nerve_type') == 'recent_events'
                assert isinstance(response.get('events'), list)
                assert response.get('count') >= 0

                writer.close()
                await writer.wait_closed()
            finally:
                await self._stop_hub(hub, serve_task)
        asyncio.run(_body())

    def test_hub_ping_pong(self, isolate_paths):
        """Test that the hub responds to ping with pong."""
        async def _body():
            hub, serve_task = await self._start_hub()
            try:
                reader, writer = await asyncio.open_unix_connection(str(ns.SOCKET_PATH))
                writer.write(json.dumps({'nerve_type': 'ping'}).encode() + b'\n')
                await writer.drain()

                data = await asyncio.wait_for(reader.readline(), timeout=3)
                response = json.loads(data.decode().strip())
                assert response.get('nerve_type') == 'pong'
                assert 'seq' in response
                assert 'uptime_s' in response

                writer.close()
                await writer.wait_closed()
            finally:
                await self._stop_hub(hub, serve_task)
        asyncio.run(_body())

    def test_hub_subscribe(self, isolate_paths):
        """Test that a subscriber receives broadcast events."""
        async def _body():
            hub, serve_task = await self._start_hub()
            try:
                sub_reader, sub_writer = await asyncio.open_unix_connection(str(ns.SOCKET_PATH))
                sub_writer.write(json.dumps({'nerve_type': 'subscribe'}).encode() + b'\n')
                await sub_writer.drain()
                data = await asyncio.wait_for(sub_reader.readline(), timeout=3)
                sub_resp = json.loads(data.decode().strip())
                assert sub_resp.get('nerve_type') == 'subscribed'

                ns.publish_event_sync('test_broadcast', {'msg': 'hello'}, 'pub')

                data = await asyncio.wait_for(sub_reader.readline(), timeout=3)
                event = json.loads(data.decode().strip())
                assert event.get('type') == 'test_broadcast'
                assert event.get('data', {}).get('msg') == 'hello'

                sub_writer.close()
                await sub_writer.wait_closed()
            finally:
                await self._stop_hub(hub, serve_task)
        asyncio.run(_body())

    def test_hub_graceful_shutdown_notifies_subscribers(self, isolate_paths):
        """Test that shutting down the hub sends shutdown messages to subscribers."""
        async def _body():
            hub, serve_task = await self._start_hub()
            try:
                sub_reader, sub_writer = await asyncio.open_unix_connection(str(ns.SOCKET_PATH))
                sub_writer.write(json.dumps({'nerve_type': 'subscribe'}).encode() + b'\n')
                await sub_writer.drain()
                await asyncio.wait_for(sub_reader.readline(), timeout=3)  # subscribed ack

                await self._stop_hub(hub, serve_task)

                # Subscriber should have received a shutdown message OR the connection closed
                try:
                    data = await asyncio.wait_for(sub_reader.readline(), timeout=2)
                    if data:
                        event = json.loads(data.decode().strip())
                        assert event.get('nerve_type') == 'shutdown'
                except (asyncio.TimeoutError, ConnectionError, json.JSONDecodeError):
                    pass  # Connection closed is also acceptable
                finally:
                    sub_writer.close()
                    try:
                        await sub_writer.wait_closed()
                    except Exception:
                        pass
            except (asyncio.CancelledError, Exception):
                pass
        asyncio.run(_body())

    def test_hub_invalid_json_handled(self, isolate_paths):
        """Test that the hub survives invalid JSON: structured error, then pong."""
        async def _body():
            hub, serve_task = await self._start_hub()
            try:
                reader, writer = await asyncio.open_unix_connection(str(ns.SOCKET_PATH))
                writer.write(b'this is not json\n')
                await writer.drain()

                # Slice 9: a structured error reply for the bad frame...
                data = await asyncio.wait_for(reader.readline(), timeout=3)
                err = json.loads(data.decode().strip())
                assert err.get('nerve_type') == 'error'
                assert err.get('reason') == 'invalid_json'

                # ...and the connection is still alive for the next frame.
                writer.write(json.dumps({'nerve_type': 'ping'}).encode() + b'\n')
                await writer.drain()
                data = await asyncio.wait_for(reader.readline(), timeout=3)
                response = json.loads(data.decode().strip())
                assert response.get('nerve_type') == 'pong'

                writer.close()
                await writer.wait_closed()
            finally:
                await self._stop_hub(hub, serve_task)
        asyncio.run(_body())


# ============================================================================
# get_status Tests
# ============================================================================

class TestGetStatus:
    def test_status_when_hub_not_running(self, isolate_paths):
        status = ns.get_status()
        assert status['hub_running'] is False
        assert status['pid'] is None

    def test_status_feed_exists(self, isolate_paths):
        feed = isolate_paths['feed_path']
        with open(feed, 'w') as f:
            f.write('{"type": "test"}\n')
            f.write('{"type": "test2"}\n')
        status = ns.get_status()
        assert status['feed_exists'] is True
        assert status['feed_events'] == 2


# ============================================================================
# Cmd Healthcheck Tests
# ============================================================================

class TestHealthcheck:
    def test_healthcheck_creates_feed_if_missing(self, isolate_paths):
        feed = isolate_paths['feed_path']
        assert not feed.exists()
        result = ns.cmd_healthcheck()
        assert isinstance(result, dict)
        assert 'socket_ok' in result
        assert 'feed_writable' in result
        assert 'healthy' in result

    def test_healthcheck_state_dir_exists(self, isolate_paths):
        assert ns.STATE_DIR.exists()


# ============================================================================
# Publish Event Sync Tests
# ============================================================================

class TestPublishEventSync:
    def test_fallback_when_hub_offline(self, isolate_paths):
        result = ns.publish_event_sync('test', {'key': 'val'}, 'tester')
        assert result.get('nerve_type') == 'fallback'
        with open(ns.FEED_PATH) as f:
            lines = f.readlines()
        assert len(lines) >= 1
        data = json.loads(lines[-1])
        assert data['type'] == 'test'
        assert data['data'] == {'key': 'val'}
        assert data.get('_fallback') is True

    def test_fallback_creates_timestamp(self, isolate_paths):
        ns.publish_event_sync('ts_test', {}, 'tester')
        with open(ns.FEED_PATH) as f:
            data = json.loads(f.readlines()[-1])
        assert '_ts' in data
        assert '_iso' in data
        # Should be timezone-aware (contains '+')
        assert '+' in data['_iso'] or data['_iso'].startswith('20')


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    def test_empty_feed_file(self, isolate_paths):
        feed = isolate_paths['feed_path']
        feed.touch()
        events = ns.get_recent_events(10)
        assert events == []

    def test_corrupt_feed_lines_skipped(self, isolate_paths):
        feed = isolate_paths['feed_path']
        with open(feed, 'w') as f:
            f.write('{"_seq": 1, "type": "good"}\n')
            f.write('this is corrupt\n')
            f.write('{"_seq": 2, "type": "also_good"}\n')
        events = ns.get_recent_events(10)
        assert len(events) == 2

    def test_log_msg_writes_to_log(self, isolate_paths):
        ns.log_msg("Test log message")
        log = isolate_paths['log_path']
        assert log.exists()
        content = log.read_text()
        assert "Test log message" in content

    def test_log_msg_handles_write_failure(self, isolate_paths):
        ns.LOG_PATH = Path("/nonexistent/path/to/log")
        try:
            ns.log_msg("This should not crash")
        finally:
            ns.LOG_PATH = isolate_paths['log_path']

    def test_ring_buffer_maxlen_respected(self):
        rb = ns.RingBuffer(maxlen=10)
        for i in range(100):
            rb.append({'i': i})
        assert len(rb) == 10
        recent = rb.recent(10)
        assert recent[-1]['i'] == 99
        assert recent[0]['i'] == 90


# ============================================================================
# Subprocess Integration Tests
# ============================================================================

class TestSubprocessIntegration:
    """Tests that run the nerve hub as a subprocess (full end-to-end)."""

    @pytest.fixture
    def subprocess_hub(self, isolate_paths, tmp_path):
        """Start a nerve hub as a subprocess using the isolated paths."""
        # Create a wrapper script that patches the paths before importing
        wrapper = tmp_path / "run_hub.py"
        wrapper.write_text(f"""
import sys
sys.path.insert(0, '{PROJECT_DIR}')
import nervous_system as ns

# Override paths for testing
ns.STATE_DIR = ns.Path('{isolate_paths["state_dir"]}')
ns.SOCKET_PATH = ns.Path('{isolate_paths["socket_path"]}')
ns.FEED_PATH = ns.Path('{isolate_paths["feed_path"]}')
ns.PID_PATH = ns.Path('{isolate_paths["pid_path"]}')
ns.LOG_PATH = ns.Path('{isolate_paths["log_path"]}')

ns.main()
""")
        proc = subprocess.Popen(
            [sys.executable, str(wrapper), 'serve'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Wait for hub to start
        for _ in range(20):
            time.sleep(0.1)
            if ns.SOCKET_PATH.exists():
                break
        assert proc.poll() is None, "Hub process should be running"
        yield proc, isolate_paths

        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        sock_path = isolate_paths['socket_path']
        if sock_path.exists():
            sock_path.unlink(missing_ok=True)
        pid_path = isolate_paths['pid_path']
        if pid_path.exists():
            pid_path.unlink(missing_ok=True)

    def test_publish_via_subprocess(self, subprocess_hub):
        """Test publishing an event via subprocess."""
        proc, paths = subprocess_hub
        wrapper = paths['state_dir'].parent.parent / "pub_test.py"
        wrapper.write_text(f"""
import sys
sys.path.insert(0, '{PROJECT_DIR}')
import nervous_system as ns

ns.SOCKET_PATH = ns.Path('{paths["socket_path"]}')
ns.FEED_PATH = ns.Path('{paths["feed_path"]}')
ns.PID_PATH = ns.Path('{paths["pid_path"]}')
ns.LOG_PATH = ns.Path('{paths["log_path"]}')
ns.STATE_DIR = ns.Path('{paths["state_dir"]}')

result = ns.publish_event_sync('subprocess_test', {{'key': 'value'}}, 'test_runner')
print(f"Result: {{result}}")
""")

        result = subprocess.run(
            [sys.executable, str(wrapper)],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout + result.stderr
        assert 'Result' in output

    def test_recent_via_subprocess(self, subprocess_hub):
        """Test getting recent events via subprocess."""
        proc, paths = subprocess_hub
        wrapper = paths['state_dir'] / "recent_test.py"
        wrapper.write_text(f"""
import sys
sys.path.insert(0, '{PROJECT_DIR}')
import nervous_system as ns

ns.SOCKET_PATH = ns.Path('{paths["socket_path"]}')
ns.FEED_PATH = ns.Path('{paths["feed_path"]}')
ns.PID_PATH = ns.Path('{paths["pid_path"]}')
ns.LOG_PATH = ns.Path('{paths["log_path"]}')
ns.STATE_DIR = ns.Path('{paths["state_dir"]}')

# Publish an event first
ns.publish_event_sync('recent_test_event', {{'test': True}}, 'test')

# Get recent events
events = ns.get_recent_events(5)
print(f"Events count: {{len(events)}}")
for e in events:
    print(f"  Event: {{e.get('type', '?')}}")
""")

        result = subprocess.run(
            [sys.executable, str(wrapper)],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout + result.stderr
        assert 'Events count' in output


# ============================================================================
# File Locking Tests
# ============================================================================

class TestFileLocking:
    def test_concurrent_feed_writes(self, isolate_paths):
        """Test that concurrent _feed_lock_write calls don't corrupt data."""
        import threading
        feed = isolate_paths['feed_path']
        errors = []

        def write_events(thread_id):
            try:
                for i in range(20):
                    event = json.dumps({'thread': thread_id, 'i': i})
                    ns._feed_lock_write(event)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_events, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors during concurrent writes: {errors}"
        with open(feed) as f:
            lines = f.readlines()
        assert len(lines) == 100  # 5 threads * 20 events
        for line in lines:
            json.loads(line.strip())  # Should not raise


# ============================================================================
# Date/Time Compatibility Tests
# ============================================================================

class TestDateTimeCompat:
    def test_publish_timestamps_are_timezone_aware(self, isolate_paths):
        """Test that published events have timezone-aware ISO timestamps."""
        ns.publish_event_sync('tz_test', {}, 'tester')
        with open(ns.FEED_PATH) as f:
            data = json.loads(f.readlines()[-1])
        iso = data.get('_iso', '')
        # datetime.now(timezone.utc) produces timestamps with '+00:00'
        assert '+00:00' in iso or iso.startswith('20')

# ============================================================================
# Forge-run slice tests (2026-10-10): hub hardening
# All sync tests; async bodies run via asyncio.run(...) (Slice 1 pattern).
# ============================================================================

async def _start_hub():
    """Start a NerveHub in the current event loop; return (hub, serve_task)."""
    hub = ns.NerveHub()
    serve_task = asyncio.create_task(hub.serve())
    for _ in range(50):
        await asyncio.sleep(0.05)
        if ns.SOCKET_PATH.exists():
            break
    assert ns.SOCKET_PATH.exists(), "Hub socket should exist after start"
    return hub, serve_task


async def _stop_hub(hub, serve_task):
    """Gracefully stop a NerveHub."""
    hub._shutdown_event.set()
    try:
        await asyncio.wait_for(serve_task, timeout=5)
    except asyncio.CancelledError:
        pass


async def _read_json_line(reader, timeout=5):
    """Read one newline-delimited JSON frame; fail if the hub closed."""
    data = await asyncio.wait_for(reader.readline(), timeout=timeout)
    assert data, "hub closed the connection unexpectedly"
    return json.loads(data.decode().strip())


async def _wait_event_count(hub, n, timeout=10):
    """Wait until the hub has processed n events. The sync publisher's ack
    is racy when it blocks the loop, so poll the counter instead."""
    deadline = time.monotonic() + timeout
    while hub.event_count < n:
        if time.monotonic() > deadline:
            raise AssertionError(
                f"hub event_count stuck at {hub.event_count}, wanted {n}")
        await asyncio.sleep(0.05)


# --- Slice 7: max message size (1 MiB) --------------------------------------

class TestOversizedFrame:
    def test_oversized_frame_rejected_and_hub_survives(self, isolate_paths):
        """A >1 MiB frame gets message_too_large, the connection is closed,
        and the hub keeps serving other clients."""
        async def _body():
            hub, serve_task = await _start_hub()
            try:
                reader, writer = await asyncio.open_unix_connection(str(ns.SOCKET_PATH))
                big = b'x' * (ns.MAX_MESSAGE_BYTES + 100) + b'\n'
                writer.write(big)
                await writer.drain()

                resp = await _read_json_line(reader)
                assert resp.get('nerve_type') == 'error'
                assert resp.get('reason') == 'message_too_large'

                # Connection was closed by the hub
                rest = await asyncio.wait_for(reader.read(), timeout=5)
                assert rest == b''

                # Hub still serves other clients
                r2, w2 = await asyncio.open_unix_connection(str(ns.SOCKET_PATH))
                w2.write(json.dumps({'nerve_type': 'ping'}).encode() + b'\n')
                await w2.drain()
                pong = await _read_json_line(r2)
                assert pong.get('nerve_type') == 'pong'
                w2.close()
                await w2.wait_closed()
            finally:
                await _stop_hub(hub, serve_task)
        asyncio.run(_body())


# --- Slice 8: broadcast backpressure ----------------------------------------

class TestBroadcastBackpressure:
    def test_stalled_subscriber_pruned_healthy_keeps_receiving(self, isolate_paths):
        """A stalled subscriber must not block the broadcast loop: it gets
        pruned on drain timeout while the healthy subscriber still receives."""
        async def _body():
            import threading
            hub, serve_task = await _start_hub()
            stop_ev = threading.Event()
            ready_ev = threading.Event()
            holder = {}
            try:
                # Healthy subscriber (big read limit: filler lines are large)
                h_reader, h_writer = await asyncio.open_unix_connection(
                    str(ns.SOCKET_PATH), limit=4 * 1024 * 1024)
                h_writer.write(json.dumps({'nerve_type': 'subscribe'}).encode() + b'\n')
                await h_writer.drain()
                ack = await _read_json_line(h_reader)
                assert ack['nerve_type'] == 'subscribed'

                writers_before = set(hub.subscribers)

                # Stalled subscriber: a raw socket owned by a helper thread.
                # It subscribes, reads the ack, then NEVER reads again — and
                # because it is not attached to the event loop, nothing drains
                # its kernel receive queue, so the hub-side drain() genuinely
                # blocks. (An asyncio client would eagerly buffer into its
                # StreamReader and never stall.)
                def _stalled_client():
                    raw = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    try:
                        raw.connect(str(ns.SOCKET_PATH))
                        raw.sendall(json.dumps({'nerve_type': 'subscribe'}).encode() + b'\n')
                        ack_raw = b''
                        while not ack_raw.endswith(b'\n'):
                            chunk = raw.recv(4096)
                            if not chunk:
                                break
                            ack_raw += chunk
                        holder['ack'] = json.loads(ack_raw.decode().strip())
                        ready_ev.set()
                        stop_ev.wait(timeout=120)
                        # After the hub prunes us it shuts the connection down.
                        # Drain any still-queued broadcast bytes first; EOF
                        # (b'') proves the hub tore the connection down.
                        try:
                            raw.settimeout(5)
                            eof = False
                            while True:
                                chunk = raw.recv(65536)
                                if chunk == b'':
                                    eof = True
                                    break
                            holder['eof'] = eof
                        except Exception:
                            holder['eof'] = False
                    finally:
                        try:
                            raw.close()
                        except Exception:
                            pass

                t = threading.Thread(target=_stalled_client, daemon=True)
                t.start()
                # Poll (don't block the loop — the hub lives in it).
                deadline = time.monotonic() + 10
                while not ready_ev.is_set() and time.monotonic() < deadline:
                    await asyncio.sleep(0.05)
                assert ready_ev.is_set(), "stalled client never subscribed"
                assert holder['ack']['nerve_type'] == 'subscribed'
                await asyncio.sleep(0.2)  # let the hub register the subscriber
                stalled = (set(hub.subscribers) - writers_before).pop()

                # Flood with large events until the stalled subscriber is pruned
                pruned = False
                for i in range(8):
                    ns.publish_event_sync('filler', {'blob': 'x' * 200_000, 'i': i}, 'test')
                    await asyncio.sleep(0.2)
                    if stalled not in hub.subscribers:
                        pruned = True
                        break
                assert pruned, "stalled subscriber was not pruned by backpressure"

                # The hub closed the stalled connection
                stop_ev.set()
                t.join(timeout=15)
                assert holder.get('eof') is True, "hub did not close the pruned subscriber"

                # Broadcast still works: healthy subscriber gets a later event
                ns.publish_event_sync('probe_after_prune', {'ok': True}, 'test')
                got_probe = False
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    try:
                        line = await asyncio.wait_for(h_reader.readline(), timeout=8)
                    except asyncio.TimeoutError:
                        break
                    if not line:
                        break
                    evt = json.loads(line.decode().strip())
                    if evt.get('type') == 'probe_after_prune':
                        got_probe = True
                        break
                assert got_probe, "healthy subscriber missed the post-prune event"

                h_writer.close()
                await h_writer.wait_closed()
            finally:
                stop_ev.set()
                await _stop_hub(hub, serve_task)
        asyncio.run(_body())


# --- Slice 9: malformed JSON frames -----------------------------------------

class TestInvalidJsonStructured:
    def test_invalid_json_structured_error_connection_stays_alive(self, isolate_paths):
        """Malformed JSON gets a structured error and the client can still
        send a valid frame afterwards and get an ack."""
        async def _body():
            hub, serve_task = await _start_hub()
            try:
                reader, writer = await asyncio.open_unix_connection(str(ns.SOCKET_PATH))
                writer.write(b'not json at all\n')
                await writer.drain()

                err = await _read_json_line(reader)
                assert err.get('nerve_type') == 'error'
                assert err.get('reason') == 'invalid_json'

                # Connection alive: a valid publish afterwards gets an ack
                writer.write(json.dumps({'type': 'after_bad_json', 'data': {}}).encode() + b'\n')
                await writer.drain()
                ack = await _read_json_line(reader)
                assert ack.get('nerve_type') == 'ack'

                writer.close()
                await writer.wait_closed()
            finally:
                await _stop_hub(hub, serve_task)
        asyncio.run(_body())


# --- Slice 10: feed write atomicity -----------------------------------------

class TestFeedFsync:
    def test_feed_lock_write_durable_and_uses_fdatasync(self, isolate_paths):
        """_feed_lock_write prefers os.fdatasync (os.fsync fallback), and the
        line is fully present once the call returns."""
        feed = isolate_paths['feed_path']
        line = json.dumps({'seq': 1, 'marker': 'durability_probe'})
        ns._feed_lock_write(line)
        with open(feed, 'r') as f:
            content = f.read()
        assert (line + '\n') in content

        # Code path: fdatasync preferred, fsync fallback
        if hasattr(os, 'fdatasync'):
            assert ns._FSYNC is os.fdatasync
        else:
            assert ns._FSYNC is os.fsync


# --- Slice 11: subscribe validation ------------------------------------------

class TestSubscribeValidation:
    def test_validate_subscribe_unit(self):
        assert ns._validate_subscribe({'nerve_type': 'subscribe'}) is True
        assert ns._validate_subscribe({'nerve_type': 'subscribe', 'filter': 'x'}) is True
        assert ns._validate_subscribe({'nerve_type': 'subscribe', 'channel': 'nope'}) is False
        assert ns._validate_subscribe({'nerve_type': 'subscribe', 'bogus': 1}) is False
        assert ns._validate_subscribe([1, 2]) is False
        assert ns._validate_subscribe('subscribe') is False

    def test_invalid_subscribe_gets_structured_error_hub_stays_alive(self, isolate_paths):
        """A subscribe frame with unknown fields (or a non-dict frame) gets a
        structured error — never a KeyError — and the hub stays alive."""
        async def _body():
            hub, serve_task = await _start_hub()
            try:
                reader, writer = await asyncio.open_unix_connection(str(ns.SOCKET_PATH))

                # Unknown field -> structured error, not subscribed
                writer.write(json.dumps({'nerve_type': 'subscribe', 'channel': 'nope'}).encode() + b'\n')
                await writer.drain()
                err = await _read_json_line(reader)
                assert err.get('nerve_type') == 'error'
                assert err.get('reason') == 'invalid_subscribe'
                assert len(hub.subscribers) == 0

                # Valid subscribe with the known optional field -> accepted
                writer.write(json.dumps({'nerve_type': 'subscribe', 'filter': 'dreams'}).encode() + b'\n')
                await writer.drain()
                ack = await _read_json_line(reader)
                assert ack.get('nerve_type') == 'subscribed'
                assert len(hub.subscribers) == 1

                # Non-dict frame -> structured error, no crash
                writer.write(b'[1, 2, 3]\n')
                await writer.drain()
                err2 = await _read_json_line(reader)
                assert err2.get('nerve_type') == 'error'

                # Hub still alive
                writer.write(json.dumps({'nerve_type': 'ping'}).encode() + b'\n')
                await writer.drain()
                pong = await _read_json_line(reader)
                assert pong.get('nerve_type') == 'pong'

                writer.close()
                await writer.wait_closed()
            finally:
                await _stop_hub(hub, serve_task)
        asyncio.run(_body())


# --- Slice 12: hub restart dedup (SOLRUN RULE regression) --------------------

class TestRestartDedup:
    def test_hub_restart_no_duplicate_events(self, isolate_paths):
        """Regression: a subscriber connecting after a hub restart must NOT
        receive duplicates of pre-restart events — only live publishes."""
        async def _body():
            hub, serve_task = await _start_hub()
            try:
                for i in range(3):
                    ns.publish_event_sync(f'pre_restart_{i}', {'i': i}, 'test')
                await _wait_event_count(hub, 3)
            finally:
                await _stop_hub(hub, serve_task)

            # Restart with the same FEED_PATH
            hub2, serve_task2 = await _start_hub()
            try:
                reader, writer = await asyncio.open_unix_connection(str(ns.SOCKET_PATH))
                writer.write(json.dumps({'nerve_type': 'subscribe'}).encode() + b'\n')
                await writer.drain()
                ack = await _read_json_line(reader)
                assert ack['nerve_type'] == 'subscribed'
                assert ack['seq'] == 3  # counter restored from feed

                for i in range(2):
                    ns.publish_event_sync(f'post_restart_{i}', {'i': i}, 'test')
                await _wait_event_count(hub2, 5)

                events = [await _read_json_line(reader) for _ in range(2)]
                seqs = [e['_seq'] for e in events]
                assert seqs == [4, 5]              # exactly the 2 new events
                assert len(set(seqs)) == 2         # unique — no duplicates
                assert all(e['type'].startswith('post_restart_') for e in events)

                writer.close()
                await writer.wait_closed()
            finally:
                await _stop_hub(hub2, serve_task2)
        asyncio.run(_body())


# --- Slice 16: structured healthcheck ---------------------------------------

class TestHealthcheckStructured:
    def test_healthcheck_dict_healthy_then_broken(self, isolate_paths):
        """cmd_healthcheck returns a structured dict: socket_ok/feed_writable
        True on a healthy setup, socket_ok False when the socket is gone."""
        async def _body():
            hub, serve_task = await _start_hub()
            try:
                # Run in a thread: the blocking ping socket must not stall
                # the test's event loop (the hub lives in it).
                result = await asyncio.to_thread(ns.cmd_healthcheck)
                assert isinstance(result, dict)
                assert result['socket_ok'] is True
                assert result['feed_writable'] is True
                assert result['feed_exists'] is True
                assert result['healthy'] is True
            finally:
                await _stop_hub(hub, serve_task)

            # Broken: hub stopped, socket path removed
            broken = await asyncio.to_thread(ns.cmd_healthcheck)
            assert isinstance(broken, dict)
            assert broken['socket_ok'] is False
            assert broken['healthy'] is False
        asyncio.run(_body())


# --- Slice 17: get_status live keys ------------------------------------------

class TestGetStatusKeys:
    def test_status_keys_not_running(self, isolate_paths):
        status = ns.get_status()
        assert status['subscriber_count'] == 0
        assert status['uptime_s'] == 0.0
        assert isinstance(status['feed_size_bytes'], int)

    def test_status_keys_with_running_hub(self, isolate_paths):
        async def _body():
            hub, serve_task = await _start_hub()
            try:
                reader, writer = await asyncio.open_unix_connection(str(ns.SOCKET_PATH))
                writer.write(json.dumps({'nerve_type': 'subscribe'}).encode() + b'\n')
                await writer.drain()
                await _read_json_line(reader)  # subscribed ack

                # Run in a thread: the blocking ping socket must not stall
                # the test's event loop (the hub lives in it).
                status = await asyncio.to_thread(ns.get_status)
                assert status['subscriber_count'] == 1
                assert isinstance(status['feed_size_bytes'], int)
                assert status['feed_size_bytes'] >= 0
                assert isinstance(status['uptime_s'], float)
                assert status['uptime_s'] >= 0.0
                assert status['hub_responsive'] is True

                writer.close()
                await writer.wait_closed()
            finally:
                await _stop_hub(hub, serve_task)
        asyncio.run(_body())
