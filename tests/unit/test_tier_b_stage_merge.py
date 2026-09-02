"""Tier B stage-merge tests (Feature 121).

For later years, the FOUNDATION models are folded into the INITIALIZATION selection
so the two stages issue ONE dbt invocation instead of two, while the FOUNDATION stage
is retained (with no models) so its validation rules + telemetry still run. The start
year is left split (FOUNDATION full-refreshes there).

These lock the invocation-shape change at the unit level; byte-level output parity is
verified separately by the deferred full-census run (tests/integration/test_tier_b_parity.py).
See specs/121-reduce-dbt-invocations/research.md Decision 4.
"""

from planalign_core.constants import (
    MODEL_INT_ACTIVE_EMPLOYEES_PREV_YEAR,
    MODEL_INT_BASELINE_WORKFORCE,
    MODEL_INT_EMPLOYEE_COMPENSATION,
)
from planalign_orchestrator.pipeline.workflow import WorkflowBuilder, WorkflowStage

START_YEAR = 2025
LATER_YEAR = 2026

# The six later-year FOUNDATION models that must survive the merge into INITIALIZATION.
LATER_FOUNDATION_MODELS = [
    "int_prev_year_workforce_summary",
    "int_prev_year_workforce_by_level",
    MODEL_INT_EMPLOYEE_COMPENSATION,
    "int_effective_parameters",
    "int_workforce_needs",
    "int_workforce_needs_by_level",
]


def _stage(workflow, name):
    return next(s for s in workflow if s.name == name)


def test_later_year_merges_foundation_into_initialization():
    workflow = WorkflowBuilder.build_year_workflow(
        year=LATER_YEAR, start_year=START_YEAR
    )
    init = _stage(workflow, WorkflowStage.INITIALIZATION)
    foundation = _stage(workflow, WorkflowStage.FOUNDATION)

    # INITIALIZATION now leads with its own model, then every FOUNDATION model.
    assert init.models[0] == MODEL_INT_ACTIVE_EMPLOYEES_PREV_YEAR
    for model in LATER_FOUNDATION_MODELS:
        assert model in init.models, f"{model} must be folded into INITIALIZATION"

    # FOUNDATION is now a 0-model stage (no separate dbt invocation) ...
    assert foundation.models == []


def test_foundation_stage_and_validations_are_preserved():
    """The merge must NOT drop the FOUNDATION stage or its validation rules (telemetry)."""
    workflow = WorkflowBuilder.build_year_workflow(
        year=LATER_YEAR, start_year=START_YEAR
    )
    foundation = _stage(workflow, WorkflowStage.FOUNDATION)

    assert foundation.validation_rules == [
        "row_count_drift",
        "compensation_reasonableness",
    ]
    # Full six-stage workflow shape is unchanged.
    assert len(workflow) == 6


def test_no_foundation_model_is_lost_in_the_merge():
    """Merged INITIALIZATION carries exactly init + the later-year foundation set."""
    workflow = WorkflowBuilder.build_year_workflow(
        year=LATER_YEAR, start_year=START_YEAR
    )
    init = _stage(workflow, WorkflowStage.INITIALIZATION)

    assert init.models == [
        MODEL_INT_ACTIVE_EMPLOYEES_PREV_YEAR,
        *LATER_FOUNDATION_MODELS,
    ]


def test_start_year_is_left_split():
    """Year 1 stays two stages, with FOUNDATION owning the baseline build.

    Tier B (feature 121) merged INITIALIZATION into FOUNDATION for later years
    and deliberately left the start year split, because start-year FOUNDATION
    carries --full-refresh and that flag applies to a whole invocation.

    Feature 132 (step 1a) then emptied start-year INITIALIZATION. That is not a
    retreat from Tier B's split — the two stages are still distinct, and
    FOUNDATION still runs its own --full-refresh invocation. It removes a build
    whose output FOUNDATION discarded moments later: INITIALIZATION built
    int_baseline_workforce incrementally, then FOUNDATION full-refreshed the
    same model. The substantive invariant is therefore stronger than before —
    int_baseline_workforce is built exactly once, by the stage that
    full-refreshes it.
    """
    workflow = WorkflowBuilder.build_year_workflow(
        year=START_YEAR, start_year=START_YEAR
    )
    init = _stage(workflow, WorkflowStage.INITIALIZATION)
    foundation = _stage(workflow, WorkflowStage.FOUNDATION)

    # Feature 132 step 1a: the redundant incremental build is gone.
    assert init.models == []
    # ...but the stage itself is retained, so its telemetry still reports.
    assert init is not None
    assert foundation.models, "start-year FOUNDATION must still build its own models"
    # The baseline build moved nowhere — FOUNDATION still owns it, exactly once.
    assert foundation.models.count(MODEL_INT_BASELINE_WORKFORCE) == 1
    # The year-1 eligibility chain is still present.
    assert "int_plan_eligibility_determination" not in foundation.models
    event_generation = next(
        stage for stage in workflow if stage.name == WorkflowStage.EVENT_GENERATION
    )
    assignment_index = event_generation.models.index(
        "int_plan_design_assignment_accumulator"
    )
    assert event_generation.models[assignment_index + 1] == (
        "int_plan_eligibility_determination"
    )


def test_calibration_workflow_untouched_by_tier_b():
    """Tier B applies only to the product workflow; the calibration path is unchanged."""
    workflow = WorkflowBuilder.build_calibration_year_workflow(
        year=LATER_YEAR, start_year=START_YEAR
    )
    foundation = _stage(workflow, WorkflowStage.FOUNDATION)
    # Calibration FOUNDATION still carries its own models (not merged/emptied).
    assert foundation.models, "calibration FOUNDATION must be unchanged by Tier B"
