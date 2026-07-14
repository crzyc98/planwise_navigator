"""Fast tests for the structured telemetry emitter (feature 094).

Contract: specs/094-live-run-dashboard/contracts/telemetry-stdout-protocol.md
"""

import io
import json
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from planalign_orchestrator.pipeline.telemetry_emitter import (
    SENTINEL,
    TelemetryEmitter,
)

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator]


@pytest.fixture
def stream():
    return io.StringIO()


@pytest.fixture
def db_manager():
    """Mock DatabaseConnectionManager whose connection yields event counts."""
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        ("HIRE", 142),
        ("TERMINATION", 98),
    ]
    manager = MagicMock()

    @contextmanager
    def get_connection(**kwargs):
        yield conn

    manager.get_connection = get_connection
    return manager


@pytest.fixture
def emitter(stream, db_manager):
    return TelemetryEmitter(db_manager=db_manager, enabled=True, stream=stream)


def records(stream):
    """Parse all sentinel records written to the stream."""
    out = []
    for line in stream.getvalue().splitlines():
        assert line.startswith(SENTINEL), f"non-sentinel line emitted: {line!r}"
        out.append(json.loads(line[len(SENTINEL) :]))
    return out


class TestGating:
    def test_disabled_by_default_without_env(self, stream, db_manager, monkeypatch):
        monkeypatch.delenv("PLANALIGN_STRUCTURED_TELEMETRY", raising=False)
        emitter = TelemetryEmitter(db_manager=db_manager, stream=stream)
        emitter.on_run_started({"start_year": 2025, "end_year": 2026})
        assert stream.getvalue() == ""

    def test_enabled_via_env(self, stream, db_manager, monkeypatch):
        monkeypatch.setenv("PLANALIGN_STRUCTURED_TELEMETRY", "1")
        emitter = TelemetryEmitter(db_manager=db_manager, stream=stream)
        emitter.on_run_started({"start_year": 2025, "end_year": 2026})
        assert len(records(stream)) == 1


class TestRecordShapes:
    def test_run_started(self, emitter, stream):
        emitter.on_run_started({"start_year": 2025, "end_year": 2027})
        (rec,) = records(stream)
        assert rec["v"] == 1
        assert rec["record"] == "run_started"
        assert rec["start_year"] == 2025
        assert rec["end_year"] == 2027
        assert rec["total_years"] == 3
        assert "ts" in rec

    def test_stage_started_uses_uppercase_stage_name(self, emitter, stream):
        from planalign_orchestrator.pipeline.workflow import WorkflowStage

        emitter.on_stage_started(
            {"year": 2025, "stage": WorkflowStage.EVENT_GENERATION}
        )
        (rec,) = records(stream)
        assert rec["record"] == "stage_started"
        assert rec["year"] == 2025
        assert rec["stage"] == "EVENT_GENERATION"

    def test_stage_completed_includes_duration(self, emitter, stream):
        from planalign_orchestrator.pipeline.workflow import WorkflowStage

        emitter.on_stage_completed(
            {"year": 2025, "stage": WorkflowStage.VALIDATION, "duration_seconds": 12.4}
        )
        (rec,) = records(stream)
        assert rec["record"] == "stage_completed"
        assert rec["stage"] == "VALIDATION"
        assert rec["duration_seconds"] == pytest.approx(12.4)

    def test_year_completed_queries_counts(self, emitter, stream):
        emitter.on_year_completed({"year": 2025, "duration_seconds": 48.2})
        (rec,) = records(stream)
        assert rec["record"] == "year_completed"
        assert rec["year"] == 2025
        assert rec["event_counts"] == {"HIRE": 142, "TERMINATION": 98}
        assert rec["cumulative_counts"] == {"HIRE": 142, "TERMINATION": 98}
        assert "workforce_reconciliation" in rec

    def test_run_id_is_propagated_from_execution_context(
        self, emitter, stream, monkeypatch
    ):
        monkeypatch.setenv("PLANALIGN_RUN_ID", "12345678-1234-5678-9234-567812345678")
        emitter.on_run_started({"start_year": 2025, "end_year": 2025})
        assert records(stream)[0]["run_id"] == "12345678-1234-5678-9234-567812345678"

    def test_validation_result_projection_is_emitted(self, emitter, stream):
        emitter.on_stage_completed(
            {
                "year": 2025,
                "stage": "VALIDATION",
                "duration_seconds": 1,
                "validation_evidence": {
                    "disposition": "passed",
                    "results": [
                        {
                            "check_name": "safe",
                            "severity": "error",
                            "passed": True,
                            "affected_record_count": 0,
                        }
                    ],
                },
            }
        )
        assert records(stream)[1]["record"] == "validation_results"
        assert records(stream)[1]["results"][0]["affected_record_count"] == 0

    def test_cumulative_counts_accumulate_across_years(self, emitter, stream):
        emitter.on_year_completed({"year": 2025, "duration_seconds": 1.0})
        emitter.on_year_completed({"year": 2026, "duration_seconds": 1.0})
        recs = records(stream)
        assert recs[1]["cumulative_counts"] == {"HIRE": 284, "TERMINATION": 196}

    def test_run_completed(self, emitter, stream):
        emitter.on_run_completed(
            {"completed_years": [2025, 2026], "duration_seconds": 151.0}
        )
        (rec,) = records(stream)
        assert rec["record"] == "run_completed"
        assert rec["years_completed"] == [2025, 2026]


class TestRobustness:
    def test_records_are_single_line(self, emitter, stream):
        emitter.on_run_started({"start_year": 2025, "end_year": 2027})
        assert stream.getvalue().count("\n") == 1

    def test_count_query_failure_does_not_raise(self, stream):
        manager = MagicMock()

        @contextmanager
        def broken(**kwargs):
            raise RuntimeError("db unavailable")
            yield  # pragma: no cover

        manager.get_connection = broken
        emitter = TelemetryEmitter(db_manager=manager, enabled=True, stream=stream)
        emitter.on_year_completed({"year": 2025, "duration_seconds": 1.0})
        (rec,) = records(stream)
        assert rec["record"] == "year_completed"
        assert rec["event_counts"] == {}

    def test_register_attaches_hooks(self, emitter):
        from planalign_orchestrator.pipeline.hooks import HookManager, HookType

        manager = HookManager()
        emitter.register(manager)
        assert manager.get_hook_count(HookType.PRE_SIMULATION) == 1
        assert manager.get_hook_count(HookType.PRE_STAGE) == 1
        assert manager.get_hook_count(HookType.POST_STAGE) == 1
        assert manager.get_hook_count(HookType.POST_YEAR) == 1
        assert manager.get_hook_count(HookType.POST_SIMULATION) == 1
