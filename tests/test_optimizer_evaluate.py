"""Optimizer candidate evaluation tests."""

from pathlib import Path

import pytest

from planalign_optimizer.evaluate import (
    classify_candidate,
    resolve_candidate_config,
    validate_levers_against_baseline,
)
from planalign_optimizer.models import (
    ConstraintSpec,
    LeverSpec,
    ObjectiveConstraintSpec,
    ObjectiveTerm,
)
from planalign_orchestrator.config import load_simulation_config, to_dbt_vars

pytestmark = pytest.mark.fast


def test_config_overlay_changes_only_declared_exported_keys() -> None:
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    candidate, delta = resolve_candidate_config(
        baseline, {"auto_enrollment.default_deferral_rate": 0.075}
    )
    before = to_dbt_vars(baseline)
    after = to_dbt_vars(candidate)
    changed = {
        key for key in before.keys() | after.keys() if before.get(key) != after.get(key)
    }
    assert changed == set(delta)
    assert "auto_enrollment_default_deferral_rate" in changed


def test_tier_one_rate_overlays_flat_active_formula() -> None:
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    candidate, delta = resolve_candidate_config(
        baseline, {"employer_match.tier_1_rate": 0.75}
    )
    assert candidate.employer_match is not None
    assert candidate.employer_match.formulas["simple_match"]["match_rate"] == 0.75
    assert "match_formulas" in delta


def test_constraint_classification_and_missing_metric() -> None:
    spec = ObjectiveConstraintSpec(
        objectives=(
            ObjectiveTerm(metric="total_employer_plan_cost", direction="minimize"),
        ),
        constraints=(
            ConstraintSpec(metric="participation_rate", operator=">=", threshold=0.85),
        ),
    )
    feasible = classify_candidate(
        "candidate-0000",
        {},
        Path("x.duckdb"),
        spec,
        {"total_employer_plan_cost": 10.0, "participation_rate": 0.9},
    )
    assert feasible.status == "feasible"
    missing = classify_candidate(
        "candidate-0001", {}, Path("x.duckdb"), spec, {"total_employer_plan_cost": 10.0}
    )
    assert missing.status == "non_evaluable"


def test_tier_two_rate_against_flat_default_baseline_fails_validation_not_a_run() -> (
    None
):
    """The shipped default baseline's active formula (simple_match) is flat.

    A ``tier_2_rate`` lever is a plausible, registry-valid choice that cannot
    resolve against that shape. It must be caught here, before any scenario
    runs, rather than raising deep inside a candidate's config resolution.
    """
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    lever = LeverSpec(
        name="employer_match.tier_2_rate", kind="continuous", bounds=(0.1, 0.9)
    )
    with pytest.raises(ValueError, match="tier_2_rate"):
        validate_levers_against_baseline(baseline, [lever])


def test_tier_one_rate_passes_baseline_validation() -> None:
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    lever = LeverSpec(
        name="employer_match.tier_1_rate", kind="continuous", bounds=(0.1, 0.9)
    )
    validate_levers_against_baseline(baseline, [lever])  # must not raise


def test_failed_candidate_is_distinct() -> None:
    spec = ObjectiveConstraintSpec(
        objectives=(ObjectiveTerm(metric="active_headcount", direction="maximize"),)
    )
    failed = classify_candidate(
        "candidate-0000", {}, None, spec, {}, failed=True, duration_seconds=1.2
    )
    assert failed.status == "failed"
    assert failed.duration_seconds == 1.2
