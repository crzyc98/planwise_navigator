"""Exceedance-risk evaluation over seed-sufficient metric distributions."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from .models import MetricDistribution, MetricSeedValue, RiskStatement, Threshold


def evaluate_thresholds(
    distributions: Sequence[MetricDistribution],
    seed_values: Sequence[MetricSeedValue],
    thresholds: Sequence[Threshold],
) -> list[RiskStatement]:
    """Evaluate strict threshold exceedance only for sufficient metric samples."""
    if not thresholds:
        return []
    by_metric: dict[str, list[MetricDistribution]] = defaultdict(list)
    for distribution in distributions:
        by_metric[distribution.metric].append(distribution)
    values = _group_values(seed_values)
    statements: list[RiskStatement] = []
    for threshold in thresholds:
        metric_distributions = by_metric.get(threshold.metric)
        if metric_distributions is None:
            statements.append(_unavailable_statement(threshold))
            continue
        statements.extend(
            _evaluate_metric_threshold(threshold, metric_distributions, values)
        )
    return statements


def _group_values(
    seed_values: Sequence[MetricSeedValue],
) -> dict[tuple[str, str, str, int], list[float]]:
    """Group non-null seed evidence at the exact aggregate grain."""
    grouped: dict[tuple[str, str, str, int], list[float]] = defaultdict(list)
    for item in seed_values:
        if item.value is not None:
            grouped[
                (
                    item.ensemble_id,
                    item.scenario_id,
                    item.metric,
                    item.simulation_year,
                )
            ].append(item.value)
    return grouped


def _evaluate_metric_threshold(
    threshold: Threshold,
    distributions: Sequence[MetricDistribution],
    values: dict[tuple[str, str, str, int], list[float]],
) -> list[RiskStatement]:
    """Return per-year probability rows, excluding insufficient distributions."""
    statements: list[RiskStatement] = []
    for distribution in sorted(distributions, key=lambda item: item.simulation_year):
        if not distribution.is_sufficient:
            continue
        key = (
            distribution.ensemble_id,
            distribution.scenario_id,
            distribution.metric,
            distribution.simulation_year,
        )
        observed = values.get(key, [])
        if not observed:
            continue
        exceeding = sum(value > threshold.value for value in observed)
        statements.append(
            RiskStatement(
                metric=threshold.metric,
                threshold_value=threshold.value,
                simulation_year=distribution.simulation_year,
                exceedance_probability=exceeding / len(observed),
                n_seeds=len(observed),
                is_evaluable=True,
            )
        )
    return statements


def _unavailable_statement(threshold: Threshold) -> RiskStatement:
    """Make an unavailable configured metric visible rather than silently absent."""
    return RiskStatement(
        metric=threshold.metric,
        threshold_value=threshold.value,
        is_evaluable=False,
        reason=f"metric '{threshold.metric}' is unavailable from these runs",
    )


__all__ = ["evaluate_thresholds"]
