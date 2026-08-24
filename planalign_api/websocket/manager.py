"""WebSocket connection manager."""

import asyncio
import logging
from typing import Awaitable, Callable, Dict, List, Set

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage WebSocket connections for simulation telemetry."""

    _SEND_TIMEOUT_SECONDS = 5.0

    def __init__(self):
        # Connections grouped by run_id
        self._connections: Dict[str, Set[WebSocket]] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, run_id: str) -> None:
        """Accept a new WebSocket connection for a run."""
        await websocket.accept()

        async with self._lock:
            if run_id not in self._connections:
                self._connections[run_id] = set()
            self._connections[run_id].add(websocket)

        logger.info(f"WebSocket connected for run {run_id}")

    async def disconnect(self, websocket: WebSocket, run_id: str) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if run_id in self._connections:
                self._connections[run_id].discard(websocket)
                if not self._connections[run_id]:
                    del self._connections[run_id]

        logger.info(f"WebSocket disconnected for run {run_id}")

    async def broadcast(self, run_id: str, message: str) -> None:
        """Broadcast a message to all connections for a run."""
        async with self._lock:
            connections = list(self._connections.get(run_id, set()))

        failed_connections = await self._send_to_connections(
            connections,
            lambda websocket: websocket.send_text(message),
            "message",
        )
        await self._remove_connections(run_id, failed_connections)

    async def broadcast_json(self, run_id: str, data: dict) -> None:
        """Broadcast JSON data to all connections for a run."""
        async with self._lock:
            connections = list(self._connections.get(run_id, set()))

        failed_connections = await self._send_to_connections(
            connections,
            lambda websocket: websocket.send_json(data),
            "JSON",
        )
        await self._remove_connections(run_id, failed_connections)

    async def _send_to_connections(
        self,
        connections: List[WebSocket],
        send: Callable[[WebSocket], Awaitable[None]],
        message_kind: str,
    ) -> List[WebSocket]:
        """Send concurrently without holding the global connection lock."""

        async def send_one(websocket: WebSocket) -> bool:
            try:
                await asyncio.wait_for(
                    send(websocket), timeout=self._SEND_TIMEOUT_SECONDS
                )
                return True
            except Exception as exc:
                logger.warning("Failed to send %s: %s", message_kind, exc)
                return False

        results = await asyncio.gather(*(send_one(ws) for ws in connections))
        return [ws for ws, succeeded in zip(connections, results) if not succeeded]

    async def _remove_connections(
        self, run_id: str, connections: List[WebSocket]
    ) -> None:
        """Remove failed sockets without replacing newer connection state."""
        if not connections:
            return

        async with self._lock:
            active_connections = self._connections.get(run_id)
            if active_connections is None:
                return

            for websocket in connections:
                active_connections.discard(websocket)
            if not active_connections:
                del self._connections[run_id]

    def get_connection_count(self, run_id: str) -> int:
        """Get number of active connections for a run."""
        return len(self._connections.get(run_id, set()))

    def get_all_run_ids(self) -> List[str]:
        """Get all run IDs with active connections."""
        return list(self._connections.keys())

    async def close_all(self, run_id: str) -> None:
        """Close all connections for a run."""
        async with self._lock:
            connections = list(self._connections.get(run_id, set()))

        async def close_one(websocket: WebSocket) -> None:
            try:
                await asyncio.wait_for(
                    websocket.close(), timeout=self._SEND_TIMEOUT_SECONDS
                )
            except (WebSocketDisconnect, ConnectionError):
                pass
            except Exception as exc:
                logger.warning(
                    "Unexpected error closing WebSocket for run %s: %s",
                    run_id,
                    exc,
                )

        await asyncio.gather(*(close_one(ws) for ws in connections))
        await self._remove_connections(run_id, connections)


# Global connection manager instance
_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """Get or create the global connection manager."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
