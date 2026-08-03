"""Fast evidence tests for one-factor-at-a-time variance attribution."""

from __future__ import annotations

from pathlib import Path

import pytest

from planalign_ensemble.attribution import (
    calculate_variance_shares,
    not_stochastic_shares,
    resolve_baselines,
)
from planalign_ensemble.models import (
    EnsembleSpec,
    MetricSeedValue,
    SeedPlan,
    SeedRunOutcome,
    Subsystem,
)


def _plan(tmp_path: Path, *, fingerprint: str = "expected") -> SeedPlan:
    spec = EnsembleSpec(
        scenario_id="attribution-fixture",
        seed_count=3,
        seed_list=(10, 20, 30),
        start_year=2029,
        end_year=2029,
        attribution=True,
        attribution_seed_count=2,
    )
    return SeedPlan(
        ensemble_id="ensemble",
        scenario_id=spec.scenario_id,
        seeds=(10, 20, 30),
        seed_db_paths={seed: tmp_path / f"seed_{seed}.duckdb" for seed in (10, 20, 30)},
        ensemble_db_path=tmp_path / "ensemble.duckdb",
        config_fingerprint=fingerprint,
        total_run_count=9,
        estimated_disk_mib=1,
        spec=spec,
    )


def _values(
    values: tuple[float, ...], *, ensemble_id: str
) -> tuple[MetricSeedValue, ...]:
    return tuple(
        MetricSeedValue(
            ensemble_id=ensemble_id,
            scenario_id="attribution-fixture",
            metric="total_employer_plan_cost",
            simulation_year=2029,
            seed=seed,
            value=value,
        )
        for seed, value in zip((10, 20, 30), values, strict=True)
    )


@pytest.mark.fast
def test_paired_variance_share_uses_only_matching_seed_evidence() -> None:
    """Freezing a fully dominant stream reduces its paired sample variance by 100%."""
    shares = calculate_variance_shares(
        _values((1.0, 3.0, 5.0), ensemble_id="baseline"),
        _values((2.0, 2.0, 2.0), ensemble_id="frozen"),
        subsystem=Subsystem.TERMINATION,
        baselines_reused=3,
        baselines_executed=0,
    )

    assert len(shares) == 1
    share = shares[0]
    assert share.n_seeds == 3
    assert share.baseline_variance == 4.0
    assert share.frozen_variance == 0.0
    assert share.variance_share == 1.0


@pytest.mark.fast
def test_reuse_guard_executes_only_seed_matches_with_different_fingerprints(
    tmp_path,
) -> None:
    """A seed is reusable only when its configuration identity matches exactly."""
    plan = _plan(tmp_path)
    plan.seed_db_paths[10].touch()
    plan.seed_db_paths[20].touch()
    headline = (
        SeedRunOutcome(
            seed=10,
            db_path=plan.seed_db_paths[10],
            status="completed",
            config_fingerprint="expected",
        ),
        SeedRunOutcome(
            seed=20,
            db_path=plan.seed_db_paths[20],
            status="completed",
            config_fingerprint="different-config",
        ),
    )
    executed: list[tuple[int, ...]] = []

    def execute(fresh_plan: SeedPlan) -> tuple[SeedRunOutcome, ...]:
        executed.append(fresh_plan.seeds)
        return tuple(
            SeedRunOutcome(
                seed=seed,
                db_path=path,
                status="completed",
                config_fingerprint="expected",
            )
            for seed, path in fresh_plan.seed_db_paths.items()
        )

    resolution = resolve_baselines(
        plan,
        headline,
        attribution_seeds=(10, 20),
        config_fingerprint="expected",
        execute=execute,
    )

    assert resolution.reused_count == 1
    assert resolution.executed_count == 1
    assert executed == [(20,)]
    assert tuple(outcome.seed for outcome in resolution.outcomes) == (10, 20)


@pytest.mark.fast
def test_reused_baseline_evidence_has_the_same_share_as_a_fresh_baseline() -> None:
    """Reuse is an I/O optimization and cannot alter the paired calculation."""
    frozen = _values((2.0, 2.0, 2.0), ensemble_id="frozen")
    reused = calculate_variance_shares(
        _values((1.0, 3.0, 5.0), ensemble_id="headline"),
        frozen,
        subsystem=Subsystem.HIRING,
        baselines_reused=3,
        baselines_executed=0,
    )
    fresh = calculate_variance_shares(
        _values((1.0, 3.0, 5.0), ensemble_id="fresh"),
        frozen,
        subsystem=Subsystem.HIRING,
        baselines_reused=0,
        baselines_executed=3,
    )

    assert reused[0].variance_share == fresh[0].variance_share
    assert reused[0].baseline_variance == fresh[0].baseline_variance
    assert reused[0].frozen_variance == fresh[0].frozen_variance


@pytest.mark.fast
def test_enrollment_and_merit_are_structurally_not_stochastic() -> None:
    """No random draw must never be rendered as a measured zero contribution."""
    shares = not_stochastic_shares(
        _values((1.0, 3.0, 5.0), ensemble_id="baseline"),
        subsystems=(Subsystem.ENROLLMENT, Subsystem.MERIT),
        baselines_reused=3,
        baselines_executed=0,
    )

    assert {share.subsystem for share in shares} == {
        Subsystem.ENROLLMENT,
        Subsystem.MERIT,
    }
    assert all(share.stochastic_status == "not_stochastic" for share in shares)
    assert all(share.variance_share is None for share in shares)
