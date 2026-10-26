"""Ordering tests for the post-termination event-generation boundary."""

from unittest.mock import MagicMock

import pytest

from planalign_orchestrator.pipeline.event_generation_executor import (
    EventGenerationExecutor,
)
from planalign_orchestrator.pipeline.workflow import WorkflowBuilder, WorkflowStage
from planalign_orchestrator.generators.enrollment import EnrollmentEventGenerator

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator]


def _event_models(year: int, start_year: int) -> list[str]:
    workflow = WorkflowBuilder.build_year_workflow(year, start_year)
    return next(
        stage.models
        for stage in workflow
        if stage.name == WorkflowStage.EVENT_GENERATION
    )


def test_termination_sources_precede_boundary_and_every_consumer() -> None:
    models = _event_models(2026, 2025)
    boundary = models.index("int_employee_termination_dates")
    assert models.index("int_termination_events") < boundary
    assert models.index("int_new_hire_termination_events") < boundary
    for consumer in (
        "int_promotion_events",
        "int_merit_events",
        "int_eligibility_events",
        "int_enrollment_events",
        "int_deferral_rate_escalation_events",
    ):
        assert boundary < models.index(consumer)


@pytest.mark.parametrize("year", [2025, 2026])
def test_workflow_and_executor_event_model_lists_are_identical(
    minimal_config, year
) -> None:
    executor = EventGenerationExecutor(
        config=minimal_config,
        dbt_runner=MagicMock(),
        db_manager=MagicMock(),
        dbt_vars={},
        event_shards=1,
    )
    workflow_models = _event_models(year, 2025)
    executor_models = executor._get_event_generation_models(year)
    assert workflow_models == executor_models
    assert "int_eligibility_events" in executor_models
    assert executor_models.index("int_deferral_change_events") == (
        executor_models.index("int_deferral_rate_escalation_events") + 1
    )
    assert "int_deferral_match_response_events" in executor_models
    assert "int_eligibility_determination" not in executor_models


def test_enrollment_generator_declares_canonical_eligibility() -> None:
    models = EnrollmentEventGenerator().get_dbt_models()
    assert "int_plan_eligibility_determination" in models
    assert "int_eligibility_determination" not in models
