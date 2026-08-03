"""Fast tests for deterministic distribution aggregation and sample gating."""

from __future__ import annotations

import pytest

from planalign_ensemble.aggregate import aggregate_ensemble
from planalign_ensemble.models import MetricSeedValue


def _values(
    observed: list[tuple[int, float | None]], *, metric: str = "total_compensation"
) -> list[MetricSeedValue]:
    """Build evidence for one metric/year without any database dependency."""
    return [
        MetricSeedValue(
            ensemble_id="ensemble",
            scenario_id="baseline",
            metric=metric,
            simulation_year=2029,
            seed=seed,
            value=value,
        )
        for seed, value in observed
    ]


@pytest.mark.fast
def test_uses_linear_percentiles_and_sample_standard_deviation() -> None:
    """Published bands match the documented NumPy linear convention."""
    distribution = aggregate_ensemble(
        _values([(42, 0.0), (1043, 10.0), (2044, 20.0), (3045, 30.0)]),
        min_seeds=4,
        n_seeds_requested=4,
    )[0]

    assert distribution.p10 == pytest.approx(3.0)
    assert distribution.p25 == pytest.approx(7.5)
    assert distribution.p50 == pytest.approx(15.0)
    assert distribution.p75 == pytest.approx(22.5)
    assert distribution.p90 == pytest.approx(27.0)
    assert distribution.mean == pytest.approx(15.0)
    assert distribution.stddev == pytest.approx(12.9099444874)
    assert distribution.percentile_method == "linear"


@pytest.mark.fast
def test_aggregation_is_bit_stable_when_inputs_arrive_in_a_different_order() -> None:
    """Seed ordering, not process completion order, defines floating-point inputs."""
    evidence = _values([(3045, 30.0), (42, 0.0), (2044, 20.0), (1043, 10.0)])

    first = aggregate_ensemble(evidence, min_seeds=4, n_seeds_requested=4)
    repeated = aggregate_ensemble(
        list(reversed(evidence)), min_seeds=4, n_seeds_requested=4
    )

    assert [item.model_dump() for item in first] == [
        item.model_dump() for item in repeated
    ]


@pytest.mark.fast
@pytest.mark.parametrize(
    ("observed", "minimum"),
    [([(42, 0.0)], 1), ([(42, 0.0), (1043, 0.0), (2044, 0.0)], 4)],
)
def test_insufficient_samples_withhold_every_band_statistic(
    observed: list[tuple[int, float]], minimum: int
) -> None:
    """NULL band fields remain distinguishable from a valid observed zero."""
    distribution = aggregate_ensemble(
        _values(observed), min_seeds=minimum, n_seeds_requested=len(observed)
    )[0]

    assert distribution.is_sufficient is False
    assert distribution.n_seeds == len(observed)
    assert (
        distribution.p10,
        distribution.p25,
        distribution.p50,
        distribution.p75,
        distribution.p90,
        distribution.mean,
        distribution.stddev,
    ) == (None, None, None, None, None, None, None)
