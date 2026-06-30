"""Fast unit tests for the comp-only calibration workflow variant (Feature 105).

Asserts that ``build_calibration_year_workflow`` rebuilds the compensation
subgraph + the two marts + the S051 growth mart, and EXCLUDES every DC model.
"""

from __future__ import annotations

import pytest

from planalign_orchestrator.pipeline.workflow import WorkflowBuilder, WorkflowStage

pytestmark = [pytest.mark.fast]

# DC models that must NOT appear in a comp-only calibration build.
_DC_MODELS = {
    "int_employer_eligibility",
    "int_eligibility_determination",
    "int_voluntary_enrollment_decision",
    "int_proactive_voluntary_enrollment",
    "int_enrollment_events",
    "int_deferral_match_response_events",
    "int_deferral_rate_escalation_events",
    "int_enrollment_state_accumulator",
    "int_deferral_rate_state_accumulator",
    "int_deferral_escalation_state_accumulator",
    "int_employee_contributions",
    "int_employer_core_contributions",
    "int_employee_match_calculations",
    "fct_employer_match_events",
    "int_synthetic_baseline_enrollment_events",
    "int_plan_eligibility_determination",
    "int_workforce_pre_enrollment",
    "int_workforce_active_for_events",
    "dq_employee_contributions_validation",
}

# Comp models that MUST be built.
_REQUIRED_COMP_MODELS = {
    "int_employee_compensation_by_year",
    "int_effective_parameters",
    "int_workforce_needs",
    "int_workforce_needs_by_level",
    "int_termination_events",
    "int_hiring_events",
    "int_hazard_promotion",
    "int_hazard_merit",
    "int_promotion_events",
    "int_merit_events",
    "fct_yearly_events",
    "int_workforce_snapshot_optimized",
    "fct_workforce_snapshot",
    "fct_compensation_growth",
}


def _all_models(year: int, start_year: int) -> set[str]:
    stages = WorkflowBuilder.build_calibration_year_workflow(year, start_year)
    models: set[str] = set()
    for stage in stages:
        models.update(stage.models)
    return models


@pytest.mark.parametrize("year,start", [(2025, 2025), (2026, 2025)])
def test_excludes_all_dc_models(year: int, start: int) -> None:
    models = _all_models(year, start)
    leaked = models & _DC_MODELS
    assert not leaked, f"DC models leaked into calibration build: {leaked}"


@pytest.mark.parametrize("year,start", [(2025, 2025), (2026, 2025)])
def test_includes_required_comp_models_and_marts(year: int, start: int) -> None:
    models = _all_models(year, start)
    missing = _REQUIRED_COMP_MODELS - models
    assert not missing, f"calibration build is missing comp models: {missing}"


def test_growth_mart_is_built() -> None:
    # fct_compensation_growth is absent from the standard workflow; calibration
    # must add it explicitly.
    assert "fct_compensation_growth" in _all_models(2025, 2025)


def test_year1_vs_year2_foundation_differs() -> None:
    y1 = WorkflowBuilder.build_calibration_year_workflow(2025, 2025)
    y2 = WorkflowBuilder.build_calibration_year_workflow(2026, 2025)
    y1_init = next(s for s in y1 if s.name == WorkflowStage.INITIALIZATION)
    y2_init = next(s for s in y2 if s.name == WorkflowStage.INITIALIZATION)
    # Year 1 seeds staging + baseline; Year 2+ uses the prev-year snapshot.
    assert "int_baseline_workforce" in y1_init.models
    assert "int_active_employees_prev_year_snapshot" in y2_init.models
    assert "int_baseline_workforce" not in y2_init.models

    y1_found = next(s for s in y1 if s.name == WorkflowStage.FOUNDATION)
    y2_found = next(s for s in y2 if s.name == WorkflowStage.FOUNDATION)
    assert "int_baseline_workforce" in y1_found.models
    assert "int_prev_year_workforce_summary" in y2_found.models
