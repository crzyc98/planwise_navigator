"""WebSocket connection manager."""

import asyncio
import logging
from typing import Dict, List, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage WebSocket connections for simulation telemetry."""

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
            if run_id not in self._connections:
                return

            dead_connections = []

            for websocket in self._connections[run_id]:
                try:
                    await websocket.send_text(message)
                except Exception as e:
                    logger.warning(f"Failed to send message: {e}")
                    dead_connections.append(websocket)

            # Clean up dead connections
            for ws in dead_connections:
                self._connections[run_id].discard(ws)

    async def broadcast_json(self, run_id: str, data: dict) -> None:
        """Broadcast JSON data to all connections for a run."""
        async with self._lock:
            if run_id not in self._connections:
                return

            dead_connections = []

            for websocket in self._connections[run_id]:
                try:
                    await websocket.send_json(data)
                except Exception as e:
                    logger.warning(f"Failed to send JSON: {e}")
                    dead_connections.append(websocket)

            # Clean up dead connections
            for ws in dead_connections:
                self._connections[run_id].discard(ws)

    def get_connection_count(self, run_id: str) -> int:
        """Get number of active connections for a run."""
        return len(self._connections.get(run_id, set()))

    def get_all_run_ids(self) -> List[str]:
        """Get all run IDs with active connections."""
        return list(self._connections.keys())

    async def close_all(self, run_id: str) -> None:
        """Close all connections for a run."""
        async with self._lock:
            if run_id not in self._connections:
                return

            for websocket in list(self._connections[run_id]):
                try:
                    await websocket.close()
                except Exception:
                    pass

            del self._connections[run_id]


# Global connection manager instance
_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """Get or create the global connection manager."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
