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


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("mode", ["automatic", "participant_elected"])
def test_auto_escalation_toggle_candidate_round_trip(enabled: bool, mode: str) -> None:
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    baseline.deferral_auto_escalation.mode = mode
    baseline.deferral_auto_escalation.enabled = not enabled
    candidate, delta = resolve_candidate_config(
        baseline, {"auto_escalation.enabled": enabled}
    )
    assert candidate.deferral_auto_escalation.enabled is enabled
    assert candidate.deferral_auto_escalation.mode == mode
    assert to_dbt_vars(candidate)["deferral_escalation_enabled"] is enabled
    assert delta == {"deferral_escalation_enabled": enabled}
    assert baseline.deferral_auto_escalation.enabled is not enabled


def test_tier_one_rate_updates_paid_match() -> None:
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    candidate, delta = resolve_candidate_config(
        baseline, {"employer_match.tier_1_rate": 0.75}
    )
    assert to_dbt_vars(candidate)["match_tiers"][0]["match_rate"] == 0.75
    assert delta["match_cap_percent"] == pytest.approx(0.0325)
    assert to_dbt_vars(baseline)["match_tiers"][0]["match_rate"] == 1.0


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


def test_missing_tier_fails_before_a_run() -> None:
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    lever = LeverSpec(
        name="employer_match.tier_3_rate", kind="continuous", bounds=(0.1, 0.9)
    )
    with pytest.raises(ValueError, match="tier_3_rate"):
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


@pytest.mark.parametrize("missing", [False, True])
def test_cap_levers_and_contiguous_tiers(missing: bool) -> None:
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    if missing:
        baseline.dc_plan = {}
    candidate, _ = resolve_candidate_config(
        baseline, {"employer_match.tier_1_cap": 0.04}
    )
    result = to_dbt_vars(candidate)
    assert result["match_tiers"][0]["employee_max"] == 0.04
    assert result["match_tiers"][1]["employee_min"] == 0.04
    assert result["match_cap_percent"] == pytest.approx(0.045)
    candidate, _ = resolve_candidate_config(
        baseline,
        {
            "employer_match.tier_1_rate": 2.0,
            "employer_match.max_match_percentage": 0.02,
        },
    )
    assert to_dbt_vars(candidate)["match_cap_percent"] == 0.02


def test_cap_past_next_tier_is_rejected() -> None:
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    with pytest.raises(ValueError, match="inverted"):
        resolve_candidate_config(
            baseline,
            {"employer_match.tier_1_cap": 0.06, "employer_match.tier_1_rate": 0.0},
        )


def test_vesting_lever_is_rejected() -> None:
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    with pytest.raises(ValueError, match="unknown optimizer lever 'vesting_schedule'"):
        resolve_candidate_config(baseline, {"vesting_schedule": "immediate"})


def test_saved_vesting_design_space_is_rejected() -> None:
    from planalign_optimizer.models import BaselineSpec, DesignSpaceSpec, OptimizerSpec
    from planalign_optimizer.spec_io import OptimizerSpecError, validate_spec

    spec = OptimizerSpec(
        baseline=BaselineSpec(config_path=Path("config/simulation_config.yaml")),
        design_space=DesignSpaceSpec(
            levers=(
                LeverSpec(
                    name="vesting_schedule", kind="discrete", choices=("immediate",)
                ),
            )
        ),
        objective=ObjectiveConstraintSpec(
            objectives=(
                ObjectiveTerm(metric="participation_rate", direction="maximize"),
            )
        ),
    )
    with pytest.raises(
        OptimizerSpecError, match="unknown optimizer lever 'vesting_schedule'"
    ):
        validate_spec(spec)
