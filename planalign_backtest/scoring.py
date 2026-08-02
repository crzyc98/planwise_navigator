"""Pure comparison arithmetic for backtest scorecards."""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping, Sequence

from planalign_backtest.models import (
    MetricComparison,
    MetricThresholds,
    MetricValue,
    SeedSpread,
    Status,
    Threshold,
    metric_definition,
)


def lower_median(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("lower_median requires at least one value")
    ordered = sorted(float(value) for value in values)
    return ordered[(len(ordered) - 1) // 2]


def score_error(predicted: float, actual: float) -> tuple[float, float | None]:
    absolute = predicted - actual
    return absolute, None if actual == 0 else absolute / actual


def classify(percent_error: float | None, threshold: Threshold) -> Status:
    if percent_error is None:
        return "undefined"
    magnitude = abs(percent_error)
    if magnitude < threshold.warn:
        return "pass"
    if magnitude < threshold.fail:
        return "warn"
    return "fail"


def seed_spread(values: Sequence[float], actual: float) -> SeedSpread | None:
    if len(values) < 2:
        return None
    normalized = tuple(float(value) for value in values)
    minimum, maximum = min(normalized), max(normalized)
    inside = minimum <= actual <= maximum
    distance = None if inside else actual - (minimum if actual < minimum else maximum)
    return SeedSpread(
        seed_count=len(normalized),
        minimum=minimum,
        maximum=maximum,
        values=normalized,
        actual_within_spread=inside,
        distance_outside=distance,
    )


def _comparison(
    key: MetricValue,
    actual: float | None,
    predictions: Sequence[float | None],
    thresholds: MetricThresholds,
) -> MetricComparison:
    definition = metric_definition(key.metric)
    threshold = thresholds.for_family(definition.family)
    if actual is None or any(value is None for value in predictions):
        reason = _unobservable_reason(definition.requires)
        return MetricComparison(
            metric=key.metric,
            period=key.period,
            family=definition.family,
            observable=False,
            unobservable_reason=reason,
            status="not_observable",
        )
    numeric_predictions = tuple(
        float(value) for value in predictions if value is not None
    )
    predicted = lower_median(numeric_predictions)
    absolute, percent = score_error(predicted, float(actual))
    return MetricComparison(
        metric=key.metric,
        period=key.period,
        family=definition.family,
        observable=True,
        predicted=predicted,
        actual=float(actual),
        absolute_error=absolute,
        percent_error=percent,
        threshold=threshold,
        status=classify(percent, threshold),
        spread=seed_spread(numeric_predictions, float(actual)),
    )


def _unobservable_reason(requirement: str | None) -> str:
    reasons = {
        "enrollment": "snapshots carry neither employee_enrollment_date nor employee_deferral_rate, so participation cannot be observed",
        "deferral": "snapshots carry no employee_deferral_rate column, so deferral levels and employer match cannot be observed",
        "level_coverage": "job-level coverage is insufficient for promotions to be observed",
    }
    if requirement is None:
        return "metric is not observable in the source census"
    return reasons.get(requirement, "metric is not observable in the source census")


def score(
    actuals: Mapping[MetricValue, float | None],
    predicted_by_seed: Sequence[Mapping[MetricValue, float | None]],
    thresholds: MetricThresholds,
) -> tuple[MetricComparison, ...]:
    if not predicted_by_seed:
        raise ValueError("scoring requires at least one seed prediction")
    observed_keys = set(actuals).union(
        *(set(predicted) for predicted in predicted_by_seed)
    )
    metrics = {key.metric for key in observed_keys}
    periods = {key.period for key in observed_keys}
    keys = sorted(
        (
            MetricValue(metric=metric, period=period)
            for metric in metrics
            for period in periods
        ),
        key=lambda key: (key.metric, str(key.period)),
    )
    comparisons = [
        _comparison(
            key,
            actuals.get(key, 0.0),
            [predicted.get(key, 0.0) for predicted in predicted_by_seed],
            thresholds,
        )
        for key in keys
    ]
    return tuple(comparisons)


def verdict_summary(comparisons: Iterable[MetricComparison]) -> tuple[str, str]:
    counts: Counter[str] = Counter(comparison.status for comparison in comparisons)
    verdict = "fail" if counts["fail"] else "warn" if counts["warn"] else "pass"
    summary = ", ".join(
        f"{counts[status]} {status.replace('_', ' ')}"
        for status in ("pass", "warn", "fail", "undefined", "not_observable")
        if counts[status]
    )
    return verdict, summary
