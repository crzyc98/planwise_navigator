"""Fast tests for WebSocket disconnect handling in the telemetry/batch streams.

Regression cover for a control-flow bug: the heartbeat send used to live inside
the ``except asyncio.TimeoutError`` handler body. Python does not route an
exception raised in one handler's body to a sibling handler of the same ``try``,
so a client that disconnected during a quiet stretch bypassed
``except WebSocketDisconnect`` and surfaced through the generic
``except Exception`` branch — logging a routine hangup as an ERROR, with an
empty message because several disconnect exceptions carry no args.

Async is driven with ``asyncio.run`` to match the convention in
``tests/api/`` and ``tests/unit/simulation/``; no async pytest plugin is
installed.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocketDisconnect

from planalign_api.websocket import handlers
from planalign_api.websocket.handlers import batch_websocket, simulation_websocket

pytestmark = [pytest.mark.fast]


@pytest.fixture
def manager():
    mgr = MagicMock()
    mgr.connect = AsyncMock()
    mgr.disconnect = AsyncMock()
    return mgr


@pytest.fixture
def telemetry():
    svc = MagicMock()
    svc.subscribe.return_value = MagicMock(get=AsyncMock())
    return svc


@pytest.fixture
def idle(monkeypatch):
    """Force the heartbeat path immediately instead of waiting out a real timeout."""

    async def instant_timeout(awaitable, timeout=None):
        # Close the coroutine we are not awaiting, so it raises no warning.
        if asyncio.iscoroutine(awaitable):
            awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(handlers.asyncio, "wait_for", instant_timeout)


def errors_in(caplog):
    return [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_disconnect_during_heartbeat_is_not_an_error(manager, telemetry, idle, caplog):
    """A hangup on the keepalive must exit cleanly, not hit the error branch."""
    websocket = MagicMock()
    websocket.send_text = AsyncMock(side_effect=WebSocketDisconnect())

    with caplog.at_level(logging.DEBUG):
        asyncio.run(
            simulation_websocket(
                websocket, "run-1", manager=manager, telemetry=telemetry
            )
        )

    assert errors_in(caplog) == []
    websocket.send_text.assert_awaited_once_with(handlers._HEARTBEAT)
    manager.disconnect.assert_awaited_once()
    telemetry.unsubscribe.assert_called_once()


def test_real_failure_still_logs_with_the_exception_type(
    manager, telemetry, idle, caplog
):
    """A genuine failure must remain an ERROR and name its type.

    Several disconnect-ish exceptions render as an empty string, so logging the
    message alone made a real failure indistinguishable from a routine hangup.
    """
    websocket = MagicMock()
    websocket.send_text = AsyncMock(side_effect=RuntimeError())

    with caplog.at_level(logging.DEBUG):
        asyncio.run(
            simulation_websocket(
                websocket, "run-2", manager=manager, telemetry=telemetry
            )
        )

    errors = errors_in(caplog)
    assert len(errors) == 1
    assert "RuntimeError" in errors[0].getMessage()
    manager.disconnect.assert_awaited_once()


def test_disconnect_delivering_telemetry_is_not_an_error(manager, telemetry, caplog):
    """The same clean exit applies when the hangup lands on a real message."""
    telemetry.subscribe.return_value = MagicMock(get=AsyncMock(return_value="{}"))
    websocket = MagicMock()
    websocket.send_text = AsyncMock(side_effect=WebSocketDisconnect())

    with caplog.at_level(logging.DEBUG):
        asyncio.run(
            simulation_websocket(
                websocket, "run-3", manager=manager, telemetry=telemetry
            )
        )

    assert errors_in(caplog) == []
    manager.disconnect.assert_awaited_once()


def test_batch_disconnect_during_heartbeat_is_not_an_error(manager, idle, caplog):
    """The batch stream carries the same shape, and the same fix."""
    websocket = MagicMock()
    websocket.receive_text = AsyncMock()
    websocket.send_text = AsyncMock(side_effect=WebSocketDisconnect())

    with caplog.at_level(logging.DEBUG):
        asyncio.run(batch_websocket(websocket, "batch-1", manager=manager))

    assert errors_in(caplog) == []
    manager.disconnect.assert_awaited_once()
