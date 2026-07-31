"""WebSocket endpoint handlers."""

import asyncio
import logging
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from .manager import ConnectionManager, get_connection_manager
from ..services.telemetry_service import TelemetryService, get_telemetry_service

logger = logging.getLogger(__name__)

# Pre-encoded so the heartbeat and telemetry paths share one send call.
_HEARTBEAT = '{"type": "heartbeat"}'


async def simulation_websocket(
    websocket: WebSocket,
    run_id: str,
    manager: Optional[ConnectionManager] = None,
    telemetry: Optional[TelemetryService] = None,
) -> None:
    """
    Handle WebSocket connection for simulation telemetry.

    Feature 094 envelope protocol (contracts/websocket-messages.md):
    every message is JSON discriminated by ``type``:

    - ``snapshot``  — full RunTelemetrySnapshot, sent once per (re)connect
                      (replayed by TelemetryService.subscribe) before deltas
    - ``update``    — incremental progress/stats (throttled server-side)
    - ``milestone`` — one appended activity-feed entry
    - ``heartbeat`` — keepalive; counts as liveness for client staleness checks

    The heartbeat interval must stay below the client's 15s staleness
    threshold so quiet stretches (long dbt model builds) don't flag stale.
    """
    if manager is None:
        manager = get_connection_manager()
    if telemetry is None:
        telemetry = get_telemetry_service()

    await manager.connect(websocket, run_id)

    # Subscribe to telemetry updates (replays a full snapshot first)
    queue = telemetry.subscribe(run_id)

    try:
        # Send telemetry updates as they arrive
        while True:
            try:
                # Wait for telemetry message with timeout
                message = await asyncio.wait_for(queue.get(), timeout=10.0)
            except asyncio.TimeoutError:
                # Quiet stretch (e.g. a long dbt model build): keepalive instead.
                message = _HEARTBEAT

            # The send is deliberately outside the timeout handler. Raising it
            # from inside an `except` body would skip the sibling
            # `except WebSocketDisconnect` below — Python does not route an
            # exception raised in one handler's body to another handler of the
            # same try — so an ordinary client disconnect during a heartbeat
            # would surface as a generic error instead of a clean break.
            try:
                await websocket.send_text(message)
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        # Client went away; the normal way a telemetry stream ends.
        logger.debug("WebSocket closed by client for run %s", run_id)

    except Exception as e:
        # Log the type: several disconnect-ish exceptions carry no message, so
        # `{e}` alone renders as an empty string and a real failure becomes
        # indistinguishable from a routine hangup.
        logger.error("WebSocket error for run %s: %s: %r", run_id, type(e).__name__, e)

    finally:
        telemetry.unsubscribe(run_id, queue)
        await manager.disconnect(websocket, run_id)


async def batch_websocket(
    websocket: WebSocket,
    batch_id: str,
    manager: Optional[ConnectionManager] = None,
) -> None:
    """
    Handle WebSocket connection for batch processing updates.

    Streams progress updates for all scenarios in a batch.

    Message format (JSON):
    {
        "batch_id": "uuid",
        "status": "running",
        "scenarios": [
            {
                "scenario_id": "baseline",
                "name": "Baseline",
                "status": "completed",
                "progress": 100
            },
            {
                "scenario_id": "high_growth",
                "name": "High Growth",
                "status": "running",
                "progress": 45
            }
        ],
        "overall_progress": 72,
        "timestamp": "2025-01-15T10:30:00Z"
    }
    """
    if manager is None:
        manager = get_connection_manager()

    await manager.connect(websocket, f"batch_{batch_id}")

    try:
        while True:
            try:
                # Wait for client messages (or heartbeat timeout)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Handle client commands if needed
                logger.debug(f"Received from batch client: {data}")
                continue

            except asyncio.TimeoutError:
                pass  # Quiet stretch; fall through to the keepalive below.

            except WebSocketDisconnect:
                break

            # Sent outside the timeout handler: an exception raised inside an
            # `except` body bypasses that try's sibling handlers, so a disconnect
            # here would never reach `except WebSocketDisconnect` above.
            try:
                await websocket.send_text(_HEARTBEAT)
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        # Client went away; the normal way a batch stream ends.
        logger.debug("WebSocket closed by client for batch %s", batch_id)

    except Exception as e:
        logger.error(
            "WebSocket error for batch %s: %s: %r", batch_id, type(e).__name__, e
        )

    finally:
        await manager.disconnect(websocket, f"batch_{batch_id}")
