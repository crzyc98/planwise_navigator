"""Stage invocation-grouping guard tests (Feature 121 — Tiers B & C).

These tests lock the *current, safe* grouping behavior so the Tier B (INIT+FOUNDATION
merge) and Tier C (STATE_ACCUMULATION split collapse) changes cannot silently break
the two invariants that keep outputs correct:

1. The STATE_ACCUMULATION full-refresh split exists only because
   ``int_workforce_snapshot_optimized`` requires ``--full-refresh`` mid-list.
2. **Critical safety invariant**: an incremental temporal accumulator
   (``int_enrollment_state_accumulator``, ``int_deferral_rate_state_accumulator``,
   ``int_deferral_escalation_state_accumulator``) must NEVER land in a
   ``--full-refresh`` group — doing so would erase prior-year state and break the
   year-N-reads-year-N-1 accumulator pattern.

The Tier C implementation (T027) MUST keep test #2 green.
"""

from planalign_orchestrator.pipeline.workflow import WorkflowBuilder, WorkflowStage
from planalign_orchestrator.pipeline.year_executor import YearExecutor


ACCUMULATORS = (
    "int_enrollment_state_accumulator",
    "int_deferral_rate_state_accumulator",
    "int_deferral_escalation_state_accumulator",
)


def _bare_executor(verbose: bool = False) -> YearExecutor:
    """A YearExecutor with just the attributes _group_models_by_full_refresh touches."""
    executor = YearExecutor.__new__(YearExecutor)
    executor.verbose = verbose
    return executor


def _state_accumulation_models(year: int = 2026) -> list:
    workflow = WorkflowBuilder.build_year_workflow(year=year, start_year=2025)
    stage = next(s for s in workflow if s.name == WorkflowStage.STATE_ACCUMULATION)
    return stage.models


def test_state_accumulation_baseline_splits_into_three_groups():
    """Baseline: the FR requirement on int_workforce_snapshot_optimized splits into 3."""
    executor = _bare_executor()
    models = _state_accumulation_models()

    groups = executor._group_models_by_full_refresh(
        models, force_full_refresh=False, year=2026
    )

    assert len(groups) == 3, (
        "Baseline STATE_ACCUMULATION grouping should be 3 (pre/full-refresh/post). "
        f"Got {[(g, fr) for g, fr in groups]}"
    )
    # Exactly one group is full-refresh, and it is int_workforce_snapshot_optimized alone.
    fr_groups = [g for g, fr in groups if fr]
    assert fr_groups == [["int_workforce_snapshot_optimized"]]


def test_incremental_accumulators_never_in_full_refresh_group():
    """SAFETY INVARIANT (must hold through Tier C): accumulators are never full-refreshed."""
    executor = _bare_executor()
    models = _state_accumulation_models()

    groups = executor._group_models_by_full_refresh(
        models, force_full_refresh=False, year=2026
    )

    for group, full_refresh in groups:
        if full_refresh:
            for accumulator in ACCUMULATORS:
                assert accumulator not in group, (
                    f"{accumulator} must never be in a --full-refresh group "
                    f"(would erase prior-year state): {group}"
                )


def test_grouping_preserves_model_order_and_membership():
    """Grouping is a pure partition: flattening the groups reproduces the input order."""
    executor = _bare_executor()
    models = _state_accumulation_models()

    groups = executor._group_models_by_full_refresh(
        models, force_full_refresh=False, year=2026
    )

    flattened = [m for group, _ in groups for m in group]
    assert flattened == models
