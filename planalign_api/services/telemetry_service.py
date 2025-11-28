"""Telemetry service for real-time simulation updates."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Set

from ..models.simulation import (
    PerformanceMetrics,
    RecentEvent,
    SimulationTelemetry,
)

logger = logging.getLogger(__name__)


class TelemetryService:
    """Service for managing real-time telemetry broadcasts."""

    def __init__(self):
        self._telemetry_data: Dict[str, SimulationTelemetry] = {}
        self._listeners: Dict[str, Set[asyncio.Queue]] = {}

    def update_telemetry(
        self,
        run_id: str,
        progress: int,
        current_stage: str,
        current_year: int,
        total_years: int,
        memory_mb: float = 0.0,
        events_generated: int = 0,
        events_per_second: float = 0.0,
        elapsed_seconds: float = 0.0,
        recent_events: Optional[list] = None,
    ) -> None:
        """Update telemetry data for a run."""
        memory_pressure = self._calculate_memory_pressure(memory_mb)

        telemetry = SimulationTelemetry(
            run_id=run_id,
            progress=progress,
            current_stage=current_stage,
            current_year=current_year,
            total_years=total_years,
            performance_metrics=PerformanceMetrics(
                memory_mb=memory_mb,
                memory_pressure=memory_pressure,
                elapsed_seconds=elapsed_seconds,
                events_generated=events_generated,
                events_per_second=events_per_second,
            ),
            recent_events=[
                RecentEvent(**e) for e in (recent_events or [])
            ],
            timestamp=datetime.utcnow(),
        )

        self._telemetry_data[run_id] = telemetry

        # Broadcast to listeners
        asyncio.create_task(self._broadcast(run_id, telemetry))

    def _calculate_memory_pressure(self, memory_mb: float) -> str:
        """Calculate memory pressure level."""
        if memory_mb < 512:
            return "low"
        elif memory_mb < 1024:
            return "moderate"
        elif memory_mb < 2048:
            return "high"
        return "critical"

    async def _broadcast(self, run_id: str, telemetry: SimulationTelemetry) -> None:
        """Broadcast telemetry to all listeners for this run."""
        if run_id not in self._listeners:
            return

        message = telemetry.model_dump_json()
        dead_queues = []

        for queue in self._listeners[run_id]:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning(f"Queue full for run {run_id}, dropping message")
            except Exception as e:
                logger.error(f"Error broadcasting to queue: {e}")
                dead_queues.append(queue)

        # Clean up dead queues
        for queue in dead_queues:
            self._listeners[run_id].discard(queue)

    def subscribe(self, run_id: str) -> asyncio.Queue:
        """Subscribe to telemetry updates for a run."""
        if run_id not in self._listeners:
            self._listeners[run_id] = set()

        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._listeners[run_id].add(queue)

        # Send current state if available
        if run_id in self._telemetry_data:
            try:
                queue.put_nowait(self._telemetry_data[run_id].model_dump_json())
            except asyncio.QueueFull:
                pass

        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        """Unsubscribe from telemetry updates."""
        if run_id in self._listeners:
            self._listeners[run_id].discard(queue)
            if not self._listeners[run_id]:
                del self._listeners[run_id]

    def get_telemetry(self, run_id: str) -> Optional[SimulationTelemetry]:
        """Get current telemetry for a run."""
        return self._telemetry_data.get(run_id)

    def clear_telemetry(self, run_id: str) -> None:
        """Clear telemetry data for a completed run."""
        self._telemetry_data.pop(run_id, None)
        self._listeners.pop(run_id, None)


# Global telemetry service instance
_telemetry_service: Optional[TelemetryService] = None


def get_telemetry_service() -> TelemetryService:
    """Get or create the global telemetry service."""
    global _telemetry_service
    if _telemetry_service is None:
        _telemetry_service = TelemetryService()
    return _telemetry_service
