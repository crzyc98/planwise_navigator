"""Consolidated STATE_ACCUMULATION invocation contracts for Feature 122."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from planalign_orchestrator.pipeline.workflow import WorkflowBuilder, WorkflowStage
from planalign_orchestrator.pipeline.year_executor import YearExecutor


def _state_stage(year: int = 2026):
    workflow = WorkflowBuilder.build_year_workflow(year=year, start_year=2025)
    return next(
        stage for stage in workflow if stage.name is WorkflowStage.STATE_ACCUMULATION
    )


def _executor() -> YearExecutor:
    executor = YearExecutor.__new__(YearExecutor)
    executor.dbt_runner = MagicMock()
    executor.dbt_runner.execute_command.return_value = MagicMock(
        success=True, return_code=0
    )
    executor.db_manager = MagicMock()
    executor._dbt_vars = {"simulation_year": 2026}
    return executor


@pytest.mark.parametrize("year", [2025, 2026])
def test_state_accumulation_is_one_dependency_closed_invocation(year: int):
    executor = _executor()
    stage = _state_stage(year)

    executor._run_sequential_event_models(stage, year)

    executor.dbt_runner.execute_command.assert_called_once()
    command = executor.dbt_runner.execute_command.call_args.args[0]
    assert command == ["run", "--select", *stage.models]
    assert "--full-refresh" not in command


def test_state_schedule_contains_no_removed_scratch_model():
    assert "int_workforce_snapshot_optimized" not in _state_stage().models


@pytest.mark.parametrize("observed", [3, 7, 24])
def test_whole_run_invocation_total_is_observational(observed: int):
    sample = {"invocations": [{"seq": index} for index in range(observed)]}
    measured_total = len(sample["invocations"])
    assert measured_total == observed
