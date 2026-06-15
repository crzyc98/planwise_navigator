"""WebSocket endpoint handlers."""

import asyncio
import logging
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from .manager import ConnectionManager, get_connection_manager
from ..services.telemetry_service import TelemetryService, get_telemetry_service

logger = logging.getLogger(__name__)


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
                await websocket.send_text(message)
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})
            except WebSocketDisconnect:
                break

    except Exception as e:
        logger.error(f"WebSocket error for run {run_id}: {e}")

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

            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})

            except WebSocketDisconnect:
                break

    except Exception as e:
        logger.error(f"WebSocket error for batch {batch_id}: {e}")

    finally:
        await manager.disconnect(websocket, f"batch_{batch_id}")
