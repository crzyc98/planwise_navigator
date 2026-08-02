"""Fast tests for pure backtest scoring."""

import pytest

from planalign_backtest.models import MetricThresholds, MetricValue, Threshold
from planalign_backtest.scoring import classify, lower_median, score, score_error

pytestmark = pytest.mark.fast


@pytest.mark.parametrize(
    ("values", "expected"),
    [((3.0,), 3.0), ((9.0, 1.0, 4.0), 4.0), ((9.0, 1.0, 4.0, 2.0), 2.0)],
)
def test_lower_median(values: tuple[float, ...], expected: float) -> None:
    assert lower_median(values) == expected
    assert lower_median(tuple(reversed(values))) == expected


def test_error_arithmetic_is_signed_and_zero_safe() -> None:
    assert score_error(110.0, 100.0) == (10.0, 0.1)
    assert score_error(90.0, 100.0) == (-10.0, -0.1)
    assert score_error(4.0, 0.0) == (4.0, None)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (0.019, "pass"),
        (0.02, "warn"),
        (-0.039, "warn"),
        (0.04, "fail"),
        (None, "undefined"),
    ],
)
def test_classify_boundaries(error: float | None, expected: str) -> None:
    assert classify(error, Threshold(warn=0.02, fail=0.04)) == expected


def test_multi_seed_spread_and_single_seed_absence() -> None:
    key = MetricValue(metric="headcount.total", period=2024)
    actuals = {key: 100.0}
    multi = score(
        actuals,
        [{key: 90.0}, {key: 110.0}, {key: 105.0}],
        MetricThresholds(),
    )[0]
    assert multi.predicted == 105.0
    assert multi.spread is not None
    assert multi.spread.values == (90.0, 110.0, 105.0)
    assert multi.spread.actual_within_spread

    single = score(actuals, [{key: 90.0}], MetricThresholds())[0]
    assert single.spread is None


def test_unobservable_propagates_and_distance_outside_is_signed() -> None:
    plan = MetricValue(metric="plan.average_deferral_rate", period=2024)
    unobservable = score({plan: None}, [{plan: 0.05}], MetricThresholds())[0]
    assert unobservable.status == "not_observable"
    assert unobservable.predicted is None

    headcount = MetricValue(metric="headcount.total", period=2024)
    comparison = score(
        {headcount: 120.0},
        [{headcount: 90.0}, {headcount: 100.0}],
        MetricThresholds(),
    )[0]
    assert comparison.spread is not None
    assert comparison.spread.distance_outside == 20.0
