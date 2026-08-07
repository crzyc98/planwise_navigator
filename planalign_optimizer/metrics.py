"""Optimizer metric vocabulary and read-only candidate metric extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import duckdb

from planalign_ensemble.extract import extract_seed_metrics
from planalign_ensemble.models import CANONICAL_METRICS
from planalign_ensemble.models import SeedRunOutcome

from .models import ConstraintSpec

SUPPORTED_METRICS: Final[tuple[str, ...]] = (*CANONICAL_METRICS, "irs_compliance_pass")
OBJECTIVE_METRICS: Final[tuple[str, ...]] = CANONICAL_METRICS


def extract_point_metrics(
    db_path: Path, year: int | None = None
) -> dict[str, float | None]:
    """Read canonical metrics for the requested or latest simulation year."""
    outcome = SeedRunOutcome(seed=0, db_path=db_path, status="completed")
    values = extract_seed_metrics(
        outcome, ensemble_id="optimizer", scenario_id="candidate"
    )
    if not values:
        return {}
    selected_year = (
        year if year is not None else max(item.simulation_year for item in values)
    )
    metrics = {
        item.metric: item.value
        for item in values
        if item.simulation_year == selected_year
    }
    metrics["irs_compliance_pass"] = _extract_compliance_pass(db_path)
    return metrics


def evaluate_constraint_metric(
    constraint: ConstraintSpec,
    point_metrics: dict[str, float | None],
    *,
    ensemble_database: Path | None = None,
    year: int | None = None,
) -> tuple[float | None, str]:
    """Resolve explicit percentile evidence, falling back visibly to point estimate."""
    if constraint.percentile is not None and ensemble_database is not None:
        percentile = _extract_percentile(
            ensemble_database, constraint.metric, constraint.percentile, year
        )
        if percentile is not None:
            return percentile, "percentile"
    return point_metrics.get(constraint.metric), "point_estimate"


def _extract_percentile(
    database: Path, metric: str, percentile: int, year: int | None
) -> float | None:
    if not database.exists():
        return None
    with duckdb.connect(str(database), read_only=True) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
        selected_year = year or _latest_metric_year(connection, tables, metric)
        if selected_year is None:
            return None
        fixed = _fixed_distribution_percentile(
            connection, tables, metric, percentile, selected_year
        )
        if fixed is not None:
            return fixed
        if "fct_metric_seed_values" not in tables:
            return None
        sources = connection.execute(
            "SELECT DISTINCT ensemble_id, scenario_id FROM fct_metric_seed_values "
            "WHERE metric = ? AND simulation_year = ? AND value IS NOT NULL",
            [metric, selected_year],
        ).fetchall()
        if len(sources) != 1:
            # Ambiguous: either no evidence, or more than one ensemble/scenario
            # sharing this metric/year in the same database. Refuse to guess
            # which one a candidate should be compared against rather than
            # silently mixing or arbitrarily picking a source.
            return None
        row = connection.execute(
            "SELECT quantile_cont(value, ?) FROM fct_metric_seed_values "
            "WHERE metric = ? AND simulation_year = ? AND value IS NOT NULL "
            "AND ensemble_id = ? AND scenario_id = ?",
            [percentile / 100.0, metric, selected_year, sources[0][0], sources[0][1]],
        ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _latest_metric_year(
    connection: duckdb.DuckDBPyConnection, tables: set[str], metric: str
) -> int | None:
    if "fct_metric_distributions" in tables:
        table = "fct_metric_distributions"
    elif "fct_metric_seed_values" in tables:
        table = "fct_metric_seed_values"
    else:
        return None
    row = connection.execute(
        f"SELECT MAX(simulation_year) FROM {table} WHERE metric = ?", [metric]
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _fixed_distribution_percentile(
    connection: duckdb.DuckDBPyConnection,
    tables: set[str],
    metric: str,
    percentile: int,
    year: int,
) -> float | None:
    if "fct_metric_distributions" not in tables or percentile not in {
        10,
        25,
        50,
        75,
        90,
    }:
        return None
    column = f"p{percentile}"
    rows = connection.execute(
        f"SELECT {column}, ensemble_id, scenario_id FROM fct_metric_distributions "
        "WHERE metric = ? AND simulation_year = ? AND is_sufficient = TRUE",
        [metric, year],
    ).fetchall()
    distinct_sources = {(row[1], row[2]) for row in rows}
    if len(distinct_sources) != 1:
        # Ambiguous for the same reason as the seed-value fallback above:
        # refuse rather than arbitrarily pick one ensemble/scenario's value.
        return None
    value = rows[0][0]
    return float(value) if value is not None else None


def _extract_compliance_pass(db_path: Path) -> float | None:
    with duckdb.connect(str(db_path), read_only=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'dq_compliance_monitoring' LIMIT 1"
        ).fetchone()
        if exists is None:
            return None
        columns = {
            str(row[0])
            for row in connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'dq_compliance_monitoring'"
            ).fetchall()
        }
        if "compliance_status" not in columns:
            return None
        failures = connection.execute(
            "SELECT COUNT(*) FROM dq_compliance_monitoring "
            "WHERE compliance_status IN ('VIOLATIONS_DETECTED', 'ADMINISTRATIVE_ISSUES')"
        ).fetchone()
    return 1.0 if failures and int(failures[0]) == 0 else 0.0
