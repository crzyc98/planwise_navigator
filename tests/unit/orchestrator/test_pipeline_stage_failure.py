from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from planalign_orchestrator.pipeline.workflow import StageDefinition, WorkflowStage
from planalign_orchestrator.pipeline_orchestrator import (
    PipelineOrchestrator,
    PipelineStageError,
)


def _foundation_stage() -> StageDefinition:
    return StageDefinition(
        name=WorkflowStage.FOUNDATION,
        dependencies=[],
        models=["model_a"],
        validation_rules=[],
    )


def _state_accumulation_stage() -> StageDefinition:
    return StageDefinition(
        name=WorkflowStage.STATE_ACCUMULATION,
        dependencies=[],
        models=["model_a"],
        validation_rules=[],
    )


def _event_generation_stage() -> StageDefinition:
    return StageDefinition(
        name=WorkflowStage.EVENT_GENERATION,
        dependencies=[],
        models=["model_a"],
        validation_rules=[],
    )


def _orchestrator_with_stage_outcome(outcome):
    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator.observability = None
    orchestrator.resource_manager = None
    orchestrator.memory_manager = None
    orchestrator.year_executor = MagicMock()
    orchestrator.year_executor.execute_workflow_stage.return_value = outcome
    orchestrator.event_generation_executor = MagicMock()
    return orchestrator


def test_execute_stage_core_raises_when_stage_reports_failure():
    orchestrator = _orchestrator_with_stage_outcome(
        {
            "stage": "foundation",
            "year": 2025,
            "success": False,
            "error": "Dbt failed",
        }
    )

    with pytest.raises(PipelineStageError):
        orchestrator._execute_stage_core(_foundation_stage(), 2025)


@pytest.mark.parametrize(
    "outcome",
    [
        None,
        {},
        {"stage": "foundation", "year": 2025},
        {"stage": "foundation", "year": 2025, "success": "false"},
    ],
)
def test_execute_stage_core_raises_for_missing_or_ambiguous_success(outcome):
    orchestrator = _orchestrator_with_stage_outcome(outcome)

    with pytest.raises(PipelineStageError):
        orchestrator._execute_stage_core(_foundation_stage(), 2025)


def test_execute_stage_core_includes_stage_year_and_error_context():
    orchestrator = _orchestrator_with_stage_outcome(
        {
            "stage": "foundation",
            "year": 2025,
            "success": False,
            "error": "missing model int_employee_compensation",
        }
    )

    with pytest.raises(PipelineStageError) as exc_info:
        orchestrator._execute_stage_core(_foundation_stage(), 2025)

    message = str(exc_info.value)
    assert "foundation" in message
    assert "2025" in message
    assert "missing model int_employee_compensation" in message


def test_execute_stage_core_uses_generic_error_when_error_missing():
    orchestrator = _orchestrator_with_stage_outcome(
        {"stage": "foundation", "year": 2025, "success": False}
    )

    with pytest.raises(PipelineStageError) as exc_info:
        orchestrator._execute_stage_core(_foundation_stage(), 2025)

    message = str(exc_info.value)
    assert "foundation" in message
    assert "2025" in message
    assert "unsuccessful" in message


def test_execute_stage_with_monitoring_propagates_stage_failure():
    orchestrator = _orchestrator_with_stage_outcome(
        {
            "stage": "foundation",
            "year": 2025,
            "success": False,
            "error": "Dbt failed",
        }
    )

    with pytest.raises(PipelineStageError):
        orchestrator._execute_stage_with_monitoring(_foundation_stage(), 2025)


def test_execute_stage_with_legacy_memory_propagates_stage_failure():
    orchestrator = _orchestrator_with_stage_outcome(
        {
            "stage": "foundation",
            "year": 2025,
            "success": False,
            "error": "Dbt failed",
        }
    )

    with pytest.raises(PipelineStageError):
        orchestrator._execute_stage_with_legacy_memory(_foundation_stage(), 2025)


@pytest.mark.parametrize(
    "outcome",
    [
        {
            "stage": "state_accumulation",
            "year": 2025,
            "success": False,
            "error": "boom",
        },
        None,
        {},
        {"stage": "state_accumulation", "year": 2025, "success": "false"},
    ],
)
def test_execute_specialized_stage_raises_for_state_accumulation_failure(outcome):
    orchestrator = _orchestrator_with_stage_outcome(outcome)

    with pytest.raises(PipelineStageError):
        orchestrator._execute_specialized_stage(_state_accumulation_stage(), 2025)


@pytest.mark.parametrize(
    "hybrid_result",
    [
        {"mode": "sql", "success": False, "execution_time": 1.0, "total_events": 0},
        None,
        {},
        {"mode": "sql", "success": "false", "execution_time": 1.0, "total_events": 0},
    ],
)
def test_execute_specialized_stage_raises_for_event_generation_failure(hybrid_result):
    orchestrator = _orchestrator_with_stage_outcome(None)
    orchestrator.event_generation_executor.execute_hybrid_event_generation.return_value = (
        hybrid_result
    )

    with pytest.raises(PipelineStageError):
        orchestrator._execute_specialized_stage(_event_generation_stage(), 2025)


def test_execute_specialized_stage_succeeds_for_state_accumulation_success():
    orchestrator = _orchestrator_with_stage_outcome(
        {"stage": "state_accumulation", "year": 2025, "success": True}
    )

    assert orchestrator._execute_specialized_stage(_state_accumulation_stage(), 2025)


def test_execute_specialized_stage_succeeds_for_event_generation_success():
    orchestrator = _orchestrator_with_stage_outcome(None)
    orchestrator.event_generation_executor.execute_hybrid_event_generation.return_value = {
        "mode": "sql",
        "success": True,
        "execution_time": 1.0,
        "total_events": 10,
    }

    assert orchestrator._execute_specialized_stage(_event_generation_stage(), 2025)
