"""Fast command-schedule contract tests for Feature 132."""

from __future__ import annotations

from collections import Counter
from unittest.mock import MagicMock

import pytest

from planalign_orchestrator.hazard_cache_manager import HazardCacheManager
from planalign_orchestrator.pipeline.workflow import WorkflowBuilder, WorkflowStage

START_YEAR = 2025
pytestmark = pytest.mark.fast


def _success() -> MagicMock:
    result = MagicMock()
    result.success = True
    return result


def _hazard_calls() -> list:
    runner = MagicMock()
    runner.execute_command.return_value = _success()
    manager = HazardCacheManager(config=MagicMock(), dbt_runner=runner)
    manager.compute_hazard_params_hash = MagicMock(return_value="a" * 64)
    manager._log_cache_statistics = MagicMock()
    manager.rebuild_hazard_caches()
    return runner.execute_command.call_args_list


def _stage_models(year: int) -> list[list[str]]:
    workflow = WorkflowBuilder.build_year_workflow(year, START_YEAR)
    return [stage.models for stage in workflow if stage.models]


def _selection(call) -> list[str]:
    args, _ = call
    command = args[0]
    start = command.index("--select") + 1
    end = (
        command.index("--full-refresh") if "--full-refresh" in command else len(command)
    )
    return command[start:end]


def test_start_year_command_count() -> None:
    setup_commands = 2 + len(_hazard_calls())  # seed + staging + hazard setup
    assert setup_commands + len(_stage_models(START_YEAR)) < 8


@pytest.mark.parametrize(
    "builder",
    [
        WorkflowBuilder.build_year_workflow,
        WorkflowBuilder.build_calibration_year_workflow,
    ],
)
def test_initialization_has_no_undeployed_validation_rules(builder) -> None:
    workflow = builder(START_YEAR, START_YEAR)
    initialization = next(
        stage for stage in workflow if stage.name is WorkflowStage.INITIALIZATION
    )

    assert initialization.validation_rules == []


def test_no_model_built_twice_per_year() -> None:
    selected = [model for models in _stage_models(START_YEAR) for model in models]
    duplicates = {model for model, count in Counter(selected).items() if count > 1}
    assert duplicates == set()


def test_full_refresh_set_unchanged() -> None:
    workflow = WorkflowBuilder.build_year_workflow(START_YEAR, START_YEAR)
    foundation = next(
        stage for stage in workflow if stage.name is WorkflowStage.FOUNDATION
    )
    hazard_models = {
        model
        for call in _hazard_calls()
        if "--full-refresh" in call.args[0]
        for model in _selection(call)
    }
    assert hazard_models | set(foundation.models) == {
        "int_effective_parameters",
        "dim_promotion_hazards",
        "dim_termination_hazards",
        "dim_merit_hazards",
        "dim_enrollment_hazards",
        "hazard_cache_metadata",
        "int_baseline_workforce",
        "int_new_hire_compensation_staging",
        "int_employee_compensation_by_year",
        "int_workforce_needs",
        "int_workforce_needs_by_level",
        "int_workforce_active_for_events",
        "int_workforce_pre_enrollment",
        "int_plan_eligibility_determination",
    }


def test_hazard_cache_vars_preserved() -> None:
    calls = _hazard_calls()
    assert calls
    for call in calls:
        assert call.kwargs["dbt_vars"] == {"hazard_params_hash": "a" * 64}
