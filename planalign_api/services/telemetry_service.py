"""Telemetry service for real-time simulation updates.

Feature 094: maintains full per-run state (snapshot, milestone history,
event counts, performance samples) in memory so reconnecting clients can be
resynchronized with a single snapshot message. Terminal states are retained
until a new run starts for the same scenario, guaranteeing clients never see
a finished run as "running".
"""

import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Optional, Set

from ..models.simulation import (
    EventTypeCounts,
    MilestoneMessage,
    PerformanceMetrics,
    PerformanceSample,
    RecentEvent,
    RunTelemetrySnapshot,
    RunTelemetryUpdate,
    SimulationLogLine,
    SimulationTelemetry,
    SnapshotMessage,
    TelemetryMilestone,
    UpdateMessage,
)

logger = logging.getLogger(__name__)

# Bounded buffers (data-model.md)
MILESTONE_CAP = 200
WARNING_MILESTONE_CAP = 20
SAMPLE_CAP = 600

_TERMINAL_STATUSES = ("completed", "failed", "cancelled")


class RunTelemetryState:
    """In-memory bookkeeping for a single run (not serialized directly)."""

    def __init__(
        self, run_id: str, scenario_id: str, start_year: int, total_years: int
    ):
        self.run_id = run_id
        self.scenario_id = scenario_id
        self.start_year = start_year
        self.total_years = total_years
        self.status: str = "running"
        self.progress: int = 0
        self.current_stage: str = "INITIALIZATION"
        self.current_year: int = start_year
        self.performance_metrics = PerformanceMetrics(
            memory_mb=0.0,
            memory_pressure="low",
            elapsed_seconds=0.0,
            events_generated=0,
            events_per_second=0.0,
        )
        self.event_counts = EventTypeCounts()
        self.milestones: Deque[TelemetryMilestone] = deque(maxlen=MILESTONE_CAP)
        self.samples: Deque[PerformanceSample] = deque(maxlen=SAMPLE_CAP)
        self.last_update_at: datetime = datetime.now(timezone.utc)
        self._sequence: int = 0
        self._warning_count: int = 0
        self._seen_log_messages: Set[str] = set()
        self._last_update_broadcast: float = 0.0

    def next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def to_snapshot(self) -> RunTelemetrySnapshot:
        return RunTelemetrySnapshot(
            run_id=self.run_id,
            scenario_id=self.scenario_id,
            status=self.status,
            progress=self.progress,
            current_stage=self.current_stage,
            current_year=self.current_year,
            total_years=self.total_years,
            start_year=self.start_year,
            performance_metrics=self.performance_metrics,
            event_counts=self.event_counts,
            milestones=list(self.milestones),
            performance_samples=list(self.samples),
            last_update_at=self.last_update_at,
        )

    def to_update(self) -> RunTelemetryUpdate:
        return RunTelemetryUpdate(
            run_id=self.run_id,
            scenario_id=self.scenario_id,
            status=self.status,
            progress=self.progress,
            current_stage=self.current_stage,
            current_year=self.current_year,
            total_years=self.total_years,
            start_year=self.start_year,
            performance_metrics=self.performance_metrics,
            event_counts=self.event_counts,
            last_update_at=self.last_update_at,
        )


class TelemetryService:
    """Service for managing real-time telemetry state and broadcasts."""

    def __init__(self):
        self._runs: Dict[str, RunTelemetryState] = {}
        self._listeners: Dict[str, Set[asyncio.Queue]] = {}
        self._min_update_interval: float = 1.0
        # Legacy storage kept for update_telemetry() compatibility
        self._telemetry_data: Dict[str, SimulationTelemetry] = {}

    # ------------------------------------------------------------------
    # Run lifecycle (feature 094)
    # ------------------------------------------------------------------

    def start_run(
        self, run_id: str, *, scenario_id: str, start_year: int, total_years: int
    ) -> None:
        """Create fresh state for a run, discarding prior runs of the scenario."""
        stale = [
            rid
            for rid, state in self._runs.items()
            if state.scenario_id == scenario_id and rid != run_id
        ]
        for rid in stale:
            self._runs.pop(rid, None)
            self._telemetry_data.pop(rid, None)

        state = RunTelemetryState(run_id, scenario_id, start_year, total_years)
        self._runs[run_id] = state
        self._append_milestone(
            state,
            kind="run_started",
            severity="info",
            year=start_year,
            message=f"Simulation started ({total_years} year"
            f"{'s' if total_years != 1 else ''} from {start_year})",
        )

    def apply_update(
        self,
        run_id: str,
        *,
        progress: int,
        current_stage: str,
        current_year: int,
        memory_mb: float = 0.0,
        events_generated: int = 0,
        events_per_second: float = 0.0,
        elapsed_seconds: float = 0.0,
    ) -> None:
        """Apply live progress values and broadcast a throttled update."""
        state = self._runs.get(run_id)
        if state is None:
            return
        state.progress = max(0, min(100, int(progress)))
        state.current_stage = current_stage or state.current_stage
        state.current_year = current_year or state.current_year
        state.performance_metrics = PerformanceMetrics(
            memory_mb=memory_mb,
            memory_pressure=self._calculate_memory_pressure(memory_mb),
            elapsed_seconds=elapsed_seconds,
            events_generated=events_generated,
            events_per_second=events_per_second,
        )
        state.last_update_at = datetime.now(timezone.utc)
        state.samples.append(
            PerformanceSample(
                timestamp=state.last_update_at,
                elapsed_seconds=elapsed_seconds,
                events_per_second=events_per_second,
                memory_mb=memory_mb,
            )
        )
        self._broadcast_update(state, force=False)

    def apply_structured_record(self, run_id: str, record: Dict[str, Any]) -> None:
        """Fold a structured telemetry record into run state and milestones."""
        state = self._runs.get(run_id)
        if state is None:
            return
        record_type = record.get("record")
        if not isinstance(record_type, str):
            return
        handlers = {
            "stage_started": self._on_stage_started,
            "stage_completed": self._on_stage_completed,
            "year_completed": self._on_year_completed,
        }
        handler = handlers.get(record_type)
        if handler is not None:
            handler(state, record)

    def add_log_milestone(self, run_id: str, severity: str, message: str) -> None:
        """Add a warning/error milestone from log output (deduped, rate-limited)."""
        state = self._runs.get(run_id)
        if state is None or severity not in ("warning", "error"):
            return
        key = message.strip()[:200]
        if key in state._seen_log_messages:
            return
        if severity == "warning":
            if state._warning_count >= WARNING_MILESTONE_CAP:
                return
            state._warning_count += 1
        state._seen_log_messages.add(key)
        self._append_milestone(
            state,
            kind=severity,
            severity=severity,
            year=state.current_year,
            stage=state.current_stage,
            message=message[:500],
        )

    def set_terminal(
        self, run_id: str, status: str, message: Optional[str] = None
    ) -> None:
        """Mark a run terminal; state is retained for reconnecting clients."""
        state = self._runs.get(run_id)
        if state is None or status not in _TERMINAL_STATUSES:
            return
        state.status = status
        if status == "completed":
            state.progress = 100
            state.current_stage = "COMPLETED"
        state.last_update_at = datetime.now(timezone.utc)
        default_messages = {
            "completed": "Simulation completed successfully",
            "failed": "Simulation failed",
            "cancelled": "Simulation cancelled by user",
        }
        self._append_milestone(
            state,
            kind="terminal",
            severity="error" if status == "failed" else "info",
            year=state.current_year,
            message=message or default_messages[status],
        )
        self._broadcast_update(state, force=True)

    def get_snapshot(self, run_id: str) -> Optional[RunTelemetrySnapshot]:
        state = self._runs.get(run_id)
        return state.to_snapshot() if state else None

    def get_snapshot_for_scenario(
        self, scenario_id: str
    ) -> Optional[RunTelemetrySnapshot]:
        for state in self._runs.values():
            if state.scenario_id == scenario_id:
                return state.to_snapshot()
        return None

    # ------------------------------------------------------------------
    # Structured record handlers
    # ------------------------------------------------------------------

    def _on_stage_started(
        self, state: RunTelemetryState, record: Dict[str, Any]
    ) -> None:
        year = record.get("year")
        stage = record.get("stage") or ""
        if isinstance(year, int):
            state.current_year = year
        if stage:
            state.current_stage = stage
        self._append_milestone(
            state,
            kind="stage_started",
            severity="info",
            year=year,
            stage=stage,
            message=f"Year {year}: {self._stage_label(stage)} started",
        )

    def _on_stage_completed(
        self, state: RunTelemetryState, record: Dict[str, Any]
    ) -> None:
        year = record.get("year")
        stage = record.get("stage") or ""
        duration = record.get("duration_seconds")
        duration_text = (
            f" ({duration:.1f}s)" if isinstance(duration, (int, float)) else ""
        )
        self._append_milestone(
            state,
            kind="stage_completed",
            severity="info",
            year=year,
            stage=stage,
            message=f"Year {year}: {self._stage_label(stage)} completed{duration_text}",
            detail={"duration_seconds": duration},
        )

    def _on_year_completed(
        self, state: RunTelemetryState, record: Dict[str, Any]
    ) -> None:
        year = record.get("year")
        year_counts = {
            k: int(v)
            for k, v in (record.get("event_counts") or {}).items()
            if isinstance(v, (int, float))
        }
        cumulative = {
            k: int(v)
            for k, v in (record.get("cumulative_counts") or {}).items()
            if isinstance(v, (int, float))
        }
        if cumulative:
            state.event_counts.by_type = cumulative
        if isinstance(year, int):
            state.event_counts.by_year[year] = year_counts
            state.event_counts.as_of_year = year
        state.event_counts.total = sum(state.event_counts.by_type.values())

        duration = record.get("duration_seconds")
        duration_text = (
            f" ({duration:.1f}s)" if isinstance(duration, (int, float)) else ""
        )
        self._append_milestone(
            state,
            kind="year_completed",
            severity="info",
            year=year,
            message=f"Year {year} complete — {self._counts_summary(year_counts)}{duration_text}",
            detail={"event_counts": year_counts, "duration_seconds": duration},
        )
        self._broadcast_update(state, force=True)

    @staticmethod
    def _stage_label(stage: str) -> str:
        return stage.replace("_", " ").title() if stage else "Stage"

    @staticmethod
    def _counts_summary(counts: Dict[str, int]) -> str:
        if not counts:
            return "no events"
        labels = {
            "HIRE": "hires",
            "TERMINATION": "terminations",
            "PROMOTION": "promotions",
            "RAISE": "raises",
            "ENROLLMENT": "enrollments",
        }
        parts = [
            f"{counts[key]} {labels[key]}"
            for key in ("HIRE", "TERMINATION", "PROMOTION", "RAISE", "ENROLLMENT")
            if key in counts
        ]
        extras = sum(v for k, v in counts.items() if k not in labels)
        if extras:
            parts.append(f"{extras} other events")
        return ", ".join(parts) if parts else "no events"

    # ------------------------------------------------------------------
    # Milestones and broadcasting
    # ------------------------------------------------------------------

    def _append_milestone(
        self,
        state: RunTelemetryState,
        *,
        kind: str,
        severity: str,
        message: str,
        year: Optional[int] = None,
        stage: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        milestone = TelemetryMilestone(
            sequence=state.next_sequence(),
            timestamp=datetime.now(timezone.utc),
            kind=kind,
            severity=severity,
            year=year,
            stage=stage,
            message=message,
            detail=detail,
        )
        state.milestones.append(milestone)
        self._send_to_listeners(
            state.run_id, MilestoneMessage(data=milestone).model_dump_json()
        )

    def _broadcast_update(self, state: RunTelemetryState, *, force: bool) -> None:
        now = time.monotonic()
        if (
            not force
            and (now - state._last_update_broadcast) < self._min_update_interval
        ):
            return
        state._last_update_broadcast = now
        self._send_to_listeners(
            state.run_id, UpdateMessage(data=state.to_update()).model_dump_json()
        )

    def _send_to_listeners(self, run_id: str, message: str) -> None:
        """Thread-safe fan-out via put_nowait (callable from worker threads)."""
        listeners = self._listeners.get(run_id)
        if not listeners:
            return
        dead_queues = []
        for queue in listeners:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("Queue full for run %s, dropping message", run_id)
            except Exception as e:
                logger.error("Error broadcasting to queue: %s", e)
                dead_queues.append(queue)
        for queue in dead_queues:
            listeners.discard(queue)

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def subscribe(self, run_id: str) -> asyncio.Queue:
        """Subscribe to telemetry updates; replays a full snapshot first."""
        if run_id not in self._listeners:
            self._listeners[run_id] = set()

        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._listeners[run_id].add(queue)

        state = self._runs.get(run_id)
        if state is not None:
            try:
                queue.put_nowait(
                    SnapshotMessage(data=state.to_snapshot()).model_dump_json()
                )
            except asyncio.QueueFull:
                pass
        elif run_id in self._telemetry_data:
            # Legacy replay for runs tracked only via update_telemetry()
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

    def has_listeners(self, run_id: str) -> bool:
        return bool(self._listeners.get(run_id))

    # ------------------------------------------------------------------
    # Legacy API (pre-094 message format, kept for compatibility)
    # ------------------------------------------------------------------

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
        recent_log_lines: Optional[list] = None,
    ) -> None:
        """Legacy entry point: stores/broadcasts the pre-094 message format.

        New code should use start_run/apply_update/apply_structured_record.
        """
        telemetry = SimulationTelemetry(
            run_id=run_id,
            progress=progress,
            current_stage=current_stage,
            current_year=current_year,
            total_years=total_years,
            performance_metrics=PerformanceMetrics(
                memory_mb=memory_mb,
                memory_pressure=self._calculate_memory_pressure(memory_mb),
                elapsed_seconds=elapsed_seconds,
                events_generated=events_generated,
                events_per_second=events_per_second,
            ),
            recent_events=[RecentEvent(**e) for e in (recent_events or [])],
            recent_log_lines=[
                ll if isinstance(ll, SimulationLogLine) else SimulationLogLine(**ll)
                for ll in (recent_log_lines or [])
            ],
            timestamp=datetime.now(timezone.utc),
        )
        self._telemetry_data[run_id] = telemetry
        self._send_to_listeners(run_id, telemetry.model_dump_json())

    def _calculate_memory_pressure(self, memory_mb: float) -> str:
        """Calculate memory pressure level."""
        if memory_mb < 512:
            return "low"
        elif memory_mb < 1024:
            return "moderate"
        elif memory_mb < 2048:
            return "high"
        return "critical"

    def get_telemetry(self, run_id: str) -> Optional[SimulationTelemetry]:
        """Get current legacy-format telemetry for a run."""
        return self._telemetry_data.get(run_id)

    def clear_telemetry(self, run_id: str) -> None:
        """Clear all state for a run (used when discarding stale runs)."""
        self._telemetry_data.pop(run_id, None)
        self._runs.pop(run_id, None)
        self._listeners.pop(run_id, None)


# Global telemetry service instance
_telemetry_service: Optional[TelemetryService] = None


def get_telemetry_service() -> TelemetryService:
    """Get or create the global telemetry service."""
    global _telemetry_service
    if _telemetry_service is None:
        _telemetry_service = TelemetryService()
    return _telemetry_service
