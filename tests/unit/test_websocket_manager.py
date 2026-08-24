"""Concurrency and cleanup tests for the WebSocket connection manager."""

import asyncio

import pytest

from planalign_api.websocket.manager import ConnectionManager

pytestmark = pytest.mark.fast


class ControlledWebSocket:
    """Small WebSocket double with controllable backpressure."""

    def __init__(self, *, blocked: bool = False, fail: bool = False):
        self.sent = []
        self._fail = fail
        self._release = asyncio.Event()
        if not blocked:
            self._release.set()

    async def accept(self):
        pass

    async def send_text(self, message):
        await self._release.wait()
        if self._fail:
            raise RuntimeError("send failed")
        self.sent.append(message)

    async def send_json(self, data):
        await self._release.wait()
        self.sent.append(data)

    async def close(self):
        self._release.set()

    def release(self):
        self._release.set()


def test_slow_client_does_not_block_telemetry_for_another_run():
    """A backpressured run cannot hold up a client on another run."""

    async def run_test():
        manager = ConnectionManager()
        manager._SEND_TIMEOUT_SECONDS = 0.05
        slow = ControlledWebSocket(blocked=True)
        fast = ControlledWebSocket()

        await manager.connect(slow, "slow-run")
        await manager.connect(fast, "fast-run")

        slow_broadcast = asyncio.create_task(manager.broadcast("slow-run", "slow"))
        await asyncio.sleep(0)
        fast_broadcast = asyncio.create_task(manager.broadcast("fast-run", "fast"))

        await asyncio.wait_for(fast_broadcast, timeout=0.1)
        assert fast.sent == ["fast"]

        await slow_broadcast
        assert manager.get_connection_count("slow-run") == 0
        assert manager.get_connection_count("fast-run") == 1

    asyncio.run(run_test())


def test_failed_cleanup_does_not_remove_a_new_connection():
    """Cleanup only discards the failed socket from the current run set."""

    async def run_test():
        manager = ConnectionManager()
        failing = ControlledWebSocket(blocked=True, fail=True)
        replacement = ControlledWebSocket()
        await manager.connect(failing, "run-1")

        broadcast = asyncio.create_task(manager.broadcast("run-1", "message"))
        await asyncio.sleep(0)
        await manager.disconnect(failing, "run-1")
        await manager.connect(replacement, "run-1")
        failing.release()
        await broadcast

        assert manager.get_connection_count("run-1") == 1
        assert replacement.sent == []

    asyncio.run(run_test())
