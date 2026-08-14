"""Read-only extraction of per-seed headline metrics from snapshot marts."""

from __future__ import annotations

from collections.abc import Iterable
from typing import SupportsFloat, cast

import duckdb

from .models import (
    CANONICAL_METRICS,
    METRIC_REGISTRY,
    MetricDefinition,
    MetricSeedValue,
    SeedRunOutcome,
)


_SNAPSHOT_TABLE = "fct_workforce_snapshot"


def extract_seed_metrics(
    outcome: SeedRunOutcome, *, ensemble_id: str, scenario_id: str
) -> list[MetricSeedValue]:
    """Read all headline metrics from one completed seed database.

    Connections are deliberately short-lived and read-only. Missing columns
    yield ``None`` values so absence can never be misreported as a zero.
    """
    if not outcome.succeeded:
        return []
    with duckdb.connect(str(outcome.db_path), read_only=True) as conn:
        if not _table_exists(conn, _SNAPSHOT_TABLE):
            return []
        columns = _table_columns(conn, _SNAPSHOT_TABLE)
        if "simulation_year" not in columns:
            return []
        rows = conn.execute(_metric_query(columns)).fetchall()
    return _to_metric_values(rows, outcome.seed, ensemble_id, scenario_id)


def extract_completed_outcomes(
    outcomes: Iterable[SeedRunOutcome], *, ensemble_id: str, scenario_id: str
) -> list[MetricSeedValue]:
    """Extract metrics in seed order from every successful terminal outcome."""
    values: list[MetricSeedValue] = []
    for outcome in sorted(outcomes, key=lambda item: item.seed):
        values.extend(
            extract_seed_metrics(
                outcome, ensemble_id=ensemble_id, scenario_id=scenario_id
            )
        )
    return values


def _table_exists(conn: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    """Check table presence without attempting to bind an absent relation."""
    row = conn.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_name = ? LIMIT 1",
        [table_name],
    ).fetchone()
    return row is not None


def _table_columns(conn: duckdb.DuckDBPyConnection, table_name: str) -> set[str]:
    """Return the supported snapshot columns in a schema-version-safe form."""
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'main' AND table_name = ?",
            [table_name],
        ).fetchall()
    }


def _metric_query(columns: set[str]) -> str:
    """Build a projection only from verified, fixed snapshot identifiers."""
    projection = ",\n                ".join(
        f"{_metric_expression(METRIC_REGISTRY[metric], columns)} AS {metric}"
        for metric in CANONICAL_METRICS
    )
    return f"""
        SELECT
            simulation_year,
            {projection}
        FROM {_SNAPSHOT_TABLE}
        GROUP BY simulation_year
        ORDER BY simulation_year
    """


def _metric_expression(definition: MetricDefinition, columns: set[str]) -> str:
    # Extraction groups by year and does not need the employee key required by
    # cohort-based evidence decompositions.
    if not set(definition.required_columns[2:]).issubset(columns):
        return "CAST(NULL AS DOUBLE)"
    if definition.kind == "active_count":
        return _active_headcount_expression(columns)
    if definition.kind == "participation":
        return _participation_expression(columns)
    if definition.kind == "average":
        assert definition.source_column is not None
        return _average_expression(columns, definition.source_column)
    assert definition.source_column is not None
    return _sum_expression(columns, definition.source_column)


def _active_headcount_expression(columns: set[str]) -> str:
    """Use the canonical active employment status where it is available."""
    if "employment_status" not in columns:
        return "CAST(NULL AS DOUBLE)"
    return "CAST(COUNT(CASE WHEN LOWER(employment_status) = 'active' THEN 1 END) AS DOUBLE)"


def _sum_expression(columns: set[str], column: str) -> str:
    """Return a nullable aggregate for a supported numeric snapshot column."""
    if column not in columns:
        return "CAST(NULL AS DOUBLE)"
    return f"CAST(SUM({column}) AS DOUBLE)"


def _average_expression(columns: set[str], column: str) -> str:
    """Return a nullable average for a supported numeric snapshot column."""
    if column not in columns:
        return "CAST(NULL AS DOUBLE)"
    return f"CAST(AVG({column}) AS DOUBLE)"


def _participation_expression(columns: set[str]) -> str:
    """Use the current participation status rather than inventing enrollment logic."""
    if "participation_status" not in columns:
        return "CAST(NULL AS DOUBLE)"
    return (
        "CAST(AVG(CASE WHEN LOWER(participation_status) = 'participating' "
        "THEN 1.0 ELSE 0.0 END) AS DOUBLE)"
    )


def _to_metric_values(
    rows: list[tuple[object, ...]], seed: int, ensemble_id: str, scenario_id: str
) -> list[MetricSeedValue]:
    """Normalize DuckDB values into explicit per-seed evidence records."""
    values: list[MetricSeedValue] = []
    for row in rows:
        year = int(cast(int | str, row[0]))
        for metric, value in zip(CANONICAL_METRICS, row[1:], strict=True):
            values.append(
                MetricSeedValue(
                    ensemble_id=ensemble_id,
                    scenario_id=scenario_id,
                    metric=metric,
                    simulation_year=year,
                    seed=seed,
                    value=(
                        float(cast(SupportsFloat | str, value))
                        if value is not None
                        else None
                    ),
                )
            )
    return values


__all__ = ["extract_completed_outcomes", "extract_seed_metrics"]
