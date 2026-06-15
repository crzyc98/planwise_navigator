"""Fast tests for per-run telemetry state in TelemetryService (feature 094).

Contracts: specs/094-live-run-dashboard/contracts/websocket-messages.md
Data model: specs/094-live-run-dashboard/data-model.md
"""

import asyncio
import json

import pytest

from planalign_api.services.telemetry_service import (
    MILESTONE_CAP,
    SAMPLE_CAP,
    WARNING_MILESTONE_CAP,
    TelemetryService,
)

pytestmark = [pytest.mark.fast]

RUN = "run-123"
SCENARIO = "scenario-abc"


@pytest.fixture
def service():
    svc = TelemetryService()
    svc._min_update_interval = 0.0  # disable throttling unless a test re-enables it
    return svc


@pytest.fixture
def started(service):
    service.start_run(RUN, scenario_id=SCENARIO, start_year=2025, total_years=3)
    return service


def drain(queue: asyncio.Queue):
    messages = []
    while True:
        try:
            messages.append(json.loads(queue.get_nowait()))
        except asyncio.QueueEmpty:
            return messages


class TestRunLifecycle:
    def test_start_run_creates_snapshot_with_run_started_milestone(self, started):
        snap = started.get_snapshot(RUN)
        assert snap is not None
        assert snap.run_id == RUN
        assert snap.scenario_id == SCENARIO
        assert snap.status == "running"
        assert snap.start_year == 2025
        assert snap.total_years == 3
        assert snap.milestones[0].kind == "run_started"
        assert snap.milestones[0].sequence == 1

    def test_terminal_state_is_retained(self, started):
        started.set_terminal(RUN, "completed")
        snap = started.get_snapshot(RUN)
        assert snap.status == "completed"
        assert snap.milestones[-1].kind == "terminal"

    def test_failed_terminal_keeps_progress(self, started):
        started.apply_update(
            RUN, progress=60, current_stage="VALIDATION", current_year=2026
        )
        started.set_terminal(RUN, "failed", message="boom")
        snap = started.get_snapshot(RUN)
        assert snap.status == "failed"
        assert snap.progress == 60

    def test_new_run_for_same_scenario_discards_old_state(self, started):
        started.set_terminal(RUN, "completed")
        started.start_run(
            "run-456", scenario_id=SCENARIO, start_year=2025, total_years=3
        )
        assert started.get_snapshot(RUN) is None
        assert started.get_snapshot("run-456").status == "running"


class TestUpdatesAndSamples:
    def test_apply_update_mutates_snapshot_and_appends_sample(self, started):
        started.apply_update(
            RUN,
            progress=42,
            current_stage="EVENT_GENERATION",
            current_year=2026,
            memory_mb=512.0,
            events_generated=1500,
            events_per_second=50.0,
            elapsed_seconds=30.5,
        )
        snap = started.get_snapshot(RUN)
        assert snap.progress == 42
        assert snap.current_stage == "EVENT_GENERATION"
        assert snap.current_year == 2026
        assert len(snap.performance_samples) == 1
        assert snap.performance_samples[0].events_per_second == 50.0

    def test_sample_ring_buffer_capped(self, started):
        for i in range(SAMPLE_CAP + 50):
            started.apply_update(
                RUN,
                progress=1,
                current_stage="FOUNDATION",
                current_year=2025,
                elapsed_seconds=float(i),
            )
        snap = started.get_snapshot(RUN)
        assert len(snap.performance_samples) == SAMPLE_CAP
        # Oldest samples dropped, newest retained
        assert snap.performance_samples[-1].elapsed_seconds == float(SAMPLE_CAP + 49)

    def test_update_broadcast_throttled(self, started):
        started._min_update_interval = 60.0
        queue = started.subscribe(RUN)
        drain(queue)  # discard snapshot
        started.apply_update(
            RUN, progress=10, current_stage="FOUNDATION", current_year=2025
        )
        started.apply_update(
            RUN, progress=11, current_stage="FOUNDATION", current_year=2025
        )
        updates = [m for m in drain(queue) if m["type"] == "update"]
        assert len(updates) == 1


class TestStructuredRecords:
    def test_stage_started_creates_milestone_and_broadcast(self, started):
        queue = started.subscribe(RUN)
        drain(queue)
        started.apply_structured_record(
            RUN, {"record": "stage_started", "year": 2025, "stage": "EVENT_GENERATION"}
        )
        snap = started.get_snapshot(RUN)
        assert snap.milestones[-1].kind == "stage_started"
        assert snap.milestones[-1].stage == "EVENT_GENERATION"
        kinds = [m["type"] for m in drain(queue)]
        assert "milestone" in kinds

    def test_year_completed_updates_counts(self, started):
        started.apply_structured_record(
            RUN,
            {
                "record": "year_completed",
                "year": 2025,
                "duration_seconds": 48.2,
                "event_counts": {"HIRE": 142, "TERMINATION": 98},
                "cumulative_counts": {"HIRE": 142, "TERMINATION": 98},
            },
        )
        snap = started.get_snapshot(RUN)
        assert snap.event_counts.by_type == {"HIRE": 142, "TERMINATION": 98}
        assert snap.event_counts.by_year[2025] == {"HIRE": 142, "TERMINATION": 98}
        assert snap.event_counts.total == 240
        assert snap.event_counts.as_of_year == 2025
        milestone = snap.milestones[-1]
        assert milestone.kind == "year_completed"
        assert milestone.detail["duration_seconds"] == pytest.approx(48.2)
        assert "142" in milestone.message and "98" in milestone.message

    def test_sequences_are_monotonic(self, started):
        started.apply_structured_record(
            RUN, {"record": "stage_started", "year": 2025, "stage": "FOUNDATION"}
        )
        started.apply_structured_record(
            RUN,
            {
                "record": "stage_completed",
                "year": 2025,
                "stage": "FOUNDATION",
                "duration_seconds": 1.0,
            },
        )
        seqs = [m.sequence for m in started.get_snapshot(RUN).milestones]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == len(seqs)


class TestLogMilestones:
    def test_warning_milestones_rate_limited(self, started):
        for i in range(WARNING_MILESTONE_CAP + 10):
            started.add_log_milestone(RUN, "warning", f"warn {i}")
        warnings = [
            m for m in started.get_snapshot(RUN).milestones if m.kind == "warning"
        ]
        assert len(warnings) == WARNING_MILESTONE_CAP

    def test_duplicate_messages_deduplicated(self, started):
        started.add_log_milestone(RUN, "warning", "same message")
        started.add_log_milestone(RUN, "warning", "same message")
        warnings = [
            m for m in started.get_snapshot(RUN).milestones if m.kind == "warning"
        ]
        assert len(warnings) == 1

    def test_milestone_list_capped(self, started):
        for i in range(MILESTONE_CAP + 50):
            started.apply_structured_record(
                RUN, {"record": "stage_started", "year": 2025, "stage": f"S{i}"}
            )
        assert len(started.get_snapshot(RUN).milestones) == MILESTONE_CAP


class TestSubscribeReplay:
    def test_subscribe_sends_snapshot_first(self, started):
        started.apply_update(
            RUN, progress=33, current_stage="FOUNDATION", current_year=2025
        )
        queue = started.subscribe(RUN)
        messages = drain(queue)
        assert messages[0]["type"] == "snapshot"
        assert messages[0]["data"]["progress"] == 33
        assert messages[0]["data"]["milestones"][0]["kind"] == "run_started"

    def test_subscribe_unknown_run_sends_nothing(self, service):
        queue = service.subscribe("nope")
        assert drain(queue) == []
