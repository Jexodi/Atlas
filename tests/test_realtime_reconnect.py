from __future__ import annotations

import asyncio
import sys
import types


if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class AsyncOpenAI:  # pragma: no cover - import compatibility stub
        pass

    openai_stub.AsyncOpenAI = AsyncOpenAI
    sys.modules["openai"] = openai_stub

from atlas.ai.realtime import RealtimeManager


class _Logger:
    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


class _EventBus:
    def __init__(self):
        self.events = []

    def publish(self, name, payload=None):
        self.events.append(name)


class _AudioOutput:
    speaking = False


class _Response:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class _HandshakeError(Exception):
    def __init__(self, status_code, headers=None):
        super().__init__(f"HTTP {status_code}")
        self.response = _Response(status_code, headers)


class _Session:
    async def update(self, session):
        self.last_session = session


class _ConnectedStream:
    def __init__(self):
        self.session = _Session()

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise asyncio.CancelledError


class _ConnectContext:
    def __init__(self, enter_result=None, enter_error=None):
        self.enter_result = enter_result
        self.enter_error = enter_error

    async def __aenter__(self):
        if self.enter_error is not None:
            raise self.enter_error
        return self.enter_result

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _RealtimeEndpoint:
    def __init__(self):
        self.calls = 0

    def connect(self, model):
        self.calls += 1
        if self.calls == 1:
            return _ConnectContext(
                enter_error=_HandshakeError(
                    429,
                    {"Retry-After": "3"},
                )
            )
        return _ConnectContext(
            enter_result=_ConnectedStream()
        )


class _Client:
    def __init__(self):
        self.realtime = _RealtimeEndpoint()


def _manager():
    return RealtimeManager(
        logger=_Logger(),
        event_bus=_EventBus(),
        audio_output=_AudioOutput(),
    )


def test_realtime_status_code_and_retry_policy():
    manager = _manager()

    assert manager._get_connection_status_code(_HandshakeError(429)) == 429
    assert manager._is_retryable_connection_error(429) is True
    assert manager._is_retryable_connection_error(500) is True
    assert manager._is_retryable_connection_error(503) is True
    assert manager._is_retryable_connection_error(None) is True
    assert manager._is_retryable_connection_error(401) is False
    assert manager._is_retryable_connection_error(403) is False
    assert manager._is_retryable_connection_error(404) is False


def test_realtime_retry_after_header_is_used():
    manager = _manager()

    assert (
        manager._get_retry_after_seconds(
            _HandshakeError(429, {"Retry-After": "7"})
        )
        == 7.0
    )
    assert manager._get_retry_after_seconds(_HandshakeError(429)) is None


def test_realtime_retries_after_429(monkeypatch):
    manager = _manager()
    manager.client = _Client()

    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def scenario():
        try:
            await manager.run()
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())

    assert manager.client.realtime.calls == 2
    assert sleeps == [60.0]
    assert "ai.realtime.connected" in manager.event_bus.events
    assert "ai.realtime.disconnected" in manager.event_bus.events
    assert manager.connected is False


def test_rate_limit_backoff_starts_at_one_minute():
    manager = _manager()

    retry_after = manager._get_retry_after_seconds(
        _HandshakeError(429, {"Retry-After": "3"})
    )

    wait_seconds = max(60.0, retry_after or 0.0, 2.0)
    assert wait_seconds == 60.0
