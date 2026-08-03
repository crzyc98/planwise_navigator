"""Fast tests for threshold exceedance risk statements."""

from __future__ import annotations

import pytest

from planalign_ensemble.models import MetricDistribution, MetricSeedValue, Threshold
from planalign_ensemble.risk import evaluate_thresholds


def _distribution(*, sufficient: bool = True) -> MetricDistribution:
    """Return one metric/year aggregate used to gate risk evaluation."""
    values = {
        "ensemble_id": "ens",
        "scenario_id": "baseline",
        "metric": "total_employer_plan_cost",
        "simulation_year": 2029,
        "n_seeds": 3 if sufficient else 1,
        "n_seeds_requested": 3,
        "is_sufficient": sufficient,
    }
    if not sufficient:
        return MetricDistribution(**values)
    return MetricDistribution(
        **values,
        p10=1.2,
        p25=1.5,
        p50=2.0,
        p75=2.5,
        p90=2.8,
        mean=2.0,
        stddev=1.0,
    )


def _seed_values() -> list[MetricSeedValue]:
    """Return a three-seed metric series with an easy direct exceedance count."""
    return [
        MetricSeedValue(
            ensemble_id="ens",
            scenario_id="baseline",
            metric="total_employer_plan_cost",
            simulation_year=2029,
            seed=seed,
            value=value,
        )
        for seed, value in ((42, 1.0), (1043, 2.0), (2044, 3.0))
    ]


@pytest.mark.fast
@pytest.mark.parametrize(
    ("threshold", "expected"),
    [(0.5, 1.0), (3.5, 0.0), (2.0, 1 / 3)],
)
def test_exceedance_boundaries_and_intermediate_counts_are_exact(
    threshold: float, expected: float
) -> None:
    """Strictly greater-than semantics match the analyst-facing statement."""
    statements = evaluate_thresholds(
        [_distribution()],
        _seed_values(),
        [Threshold(metric="total_employer_plan_cost", value=threshold)],
    )

    assert len(statements) == 1
    assert statements[0].is_evaluable is True
    assert statements[0].exceedance_probability == pytest.approx(expected)
    assert statements[0].n_seeds == 3


@pytest.mark.fast
def test_unavailable_metric_is_reported_not_evaluable_with_its_name() -> None:
    """A typo or disabled metric must not silently look like zero risk."""
    statements = evaluate_thresholds(
        [_distribution()], _seed_values(), [Threshold(metric="missing_metric", value=1)]
    )

    assert len(statements) == 1
    assert statements[0].is_evaluable is False
    assert "missing_metric" in (statements[0].reason or "")


@pytest.mark.fast
def test_insufficient_sample_metric_is_excluded_from_risk_evaluation() -> None:
    """Thin distributions cannot create a probability-shaped number."""
    statements = evaluate_thresholds(
        [_distribution(sufficient=False)],
        _seed_values(),
        [Threshold(metric="total_employer_plan_cost", value=2)],
    )

    assert statements == []
