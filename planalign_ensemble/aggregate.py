"""Deterministic aggregate construction and dedicated ensemble-DB persistence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path

import duckdb
import numpy as np

from .models import MetricDistribution, MetricSeedValue


_PERCENTILES = (10, 25, 50, 75, 90)

_CREATE_DISTRIBUTIONS_SQL = """
CREATE TABLE IF NOT EXISTS fct_metric_distributions (
    ensemble_id VARCHAR NOT NULL,
    scenario_id VARCHAR NOT NULL,
    metric VARCHAR NOT NULL,
    simulation_year INTEGER NOT NULL,
    p10 DOUBLE,
    p25 DOUBLE,
    p50 DOUBLE,
    p75 DOUBLE,
    p90 DOUBLE,
    mean DOUBLE,
    stddev DOUBLE,
    n_seeds INTEGER NOT NULL,
    n_seeds_requested INTEGER NOT NULL,
    is_sufficient BOOLEAN NOT NULL,
    percentile_method VARCHAR NOT NULL,
    PRIMARY KEY (ensemble_id, scenario_id, metric, simulation_year)
)
"""

_CREATE_SEED_VALUES_SQL = """
CREATE TABLE IF NOT EXISTS fct_metric_seed_values (
    ensemble_id VARCHAR NOT NULL,
    scenario_id VARCHAR NOT NULL,
    metric VARCHAR NOT NULL,
    simulation_year INTEGER NOT NULL,
    seed BIGINT NOT NULL,
    value DOUBLE,
    PRIMARY KEY (ensemble_id, scenario_id, metric, simulation_year, seed)
)
"""


def aggregate_ensemble(
    seed_values: Sequence[MetricSeedValue],
    *,
    min_seeds: int,
    n_seeds_requested: int | None = None,
) -> list[MetricDistribution]:
    """Compute linear bands over seed-sorted values at every metric/year grain."""
    if min_seeds < 1:
        raise ValueError("min_seeds must be >= 1")
    requested = n_seeds_requested or _infer_requested_seed_count(seed_values)
    if requested < 1:
        return []
    grouped: dict[tuple[str, str, str, int], list[MetricSeedValue]] = defaultdict(list)
    for value in seed_values:
        grouped[
            (
                value.ensemble_id,
                value.scenario_id,
                value.metric,
                value.simulation_year,
            )
        ].append(value)
    return [
        _aggregate_group(key, grouped[key], min_seeds, requested)
        for key in sorted(grouped)
    ]


def write_ensemble_results(
    ensemble_db_path: Path,
    distributions: Iterable[MetricDistribution],
    seed_values: Iterable[MetricSeedValue],
) -> None:
    """Write immutable aggregate evidence to the dedicated ensemble database.

    This function never opens a seed database for writing. Primary keys make a
    duplicate write fail loudly instead of silently revising prior evidence.
    """
    distribution_rows = [
        (
            item.ensemble_id,
            item.scenario_id,
            item.metric,
            item.simulation_year,
            item.p10,
            item.p25,
            item.p50,
            item.p75,
            item.p90,
            item.mean,
            item.stddev,
            item.n_seeds,
            item.n_seeds_requested,
            item.is_sufficient,
            item.percentile_method,
        )
        for item in distributions
    ]
    seed_rows = [
        (
            item.ensemble_id,
            item.scenario_id,
            item.metric,
            item.simulation_year,
            item.seed,
            item.value,
        )
        for item in seed_values
    ]
    ensemble_db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(ensemble_db_path)) as conn:
        conn.execute("BEGIN TRANSACTION")
        try:
            conn.execute(_CREATE_DISTRIBUTIONS_SQL)
            conn.execute(_CREATE_SEED_VALUES_SQL)
            if seed_rows:
                conn.executemany(
                    "INSERT INTO fct_metric_seed_values VALUES (?, ?, ?, ?, ?, ?)",
                    seed_rows,
                )
            if distribution_rows:
                conn.executemany(
                    "INSERT INTO fct_metric_distributions VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    distribution_rows,
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


def _infer_requested_seed_count(seed_values: Sequence[MetricSeedValue]) -> int:
    """Infer an evidence-set size for callers aggregating a complete result set."""
    return len({item.seed for item in seed_values})


def _aggregate_group(
    key: tuple[str, str, str, int],
    values: Sequence[MetricSeedValue],
    min_seeds: int,
    n_seeds_requested: int,
) -> MetricDistribution:
    """Build one distribution while preserving missing metric values as NULL."""
    ordered = sorted(values, key=lambda item: item.seed)
    _ensure_unique_seeds(ordered, key)
    observed = np.asarray(
        [item.value for item in ordered if item.value is not None], dtype=float
    )
    sufficient = len(observed) >= max(min_seeds, 2)
    common = {
        "ensemble_id": key[0],
        "scenario_id": key[1],
        "metric": key[2],
        "simulation_year": key[3],
        "n_seeds": int(len(observed)),
        "n_seeds_requested": n_seeds_requested,
        "is_sufficient": sufficient,
    }
    if not sufficient:
        return MetricDistribution(**common)
    percentile_values = np.percentile(observed, _PERCENTILES, method="linear")
    return MetricDistribution(
        **common,
        p10=float(percentile_values[0]),
        p25=float(percentile_values[1]),
        p50=float(percentile_values[2]),
        p75=float(percentile_values[3]),
        p90=float(percentile_values[4]),
        mean=float(np.mean(observed)),
        stddev=float(np.std(observed, ddof=1)),
    )


def _ensure_unique_seeds(
    values: Sequence[MetricSeedValue], key: tuple[str, str, str, int]
) -> None:
    """Reject duplicate evidence rows before they can understate the spread."""
    seeds = [item.seed for item in values]
    if len(seeds) != len(set(seeds)):
        raise ValueError(f"duplicate seed evidence for metric distribution {key}")


__all__ = ["aggregate_ensemble", "write_ensemble_results"]
