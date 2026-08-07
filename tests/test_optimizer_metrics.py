"""Optimizer metric evaluation tests."""

from pathlib import Path

import duckdb
import pytest

from planalign_optimizer.metrics import (
    evaluate_constraint_metric,
    extract_point_metrics,
)
from planalign_optimizer.models import ConstraintSpec

pytestmark = pytest.mark.fast


def test_percentile_is_explicit_and_falls_back_when_unavailable(tmp_path: Path) -> None:
    point = ConstraintSpec(metric="participation_rate", operator=">=", threshold=0.8)
    assert evaluate_constraint_metric(point, {"participation_rate": 0.85}) == (
        0.85,
        "point_estimate",
    )
    requested = point.model_copy(update={"percentile": 90})
    assert evaluate_constraint_metric(requested, {"participation_rate": 0.85}) == (
        0.85,
        "point_estimate",
    )

    database = tmp_path / "ensemble.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "CREATE TABLE fct_metric_seed_values(ensemble_id VARCHAR, scenario_id VARCHAR, "
            "metric VARCHAR, simulation_year INTEGER, seed INTEGER, value DOUBLE)"
        )
        connection.executemany(
            "INSERT INTO fct_metric_seed_values VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("e", "s", "participation_rate", 2025, 1, 0.7),
                ("e", "s", "participation_rate", 2025, 2, 0.9),
            ],
        )
    value, mode = evaluate_constraint_metric(
        requested, {"participation_rate": 0.85}, ensemble_database=database
    )
    assert mode == "percentile"
    assert value == pytest.approx(0.88)


def test_percentile_refuses_to_guess_across_multiple_sources(tmp_path: Path) -> None:
    """Two ensembles/scenarios sharing a metric/year must not be silently mixed."""
    requested = ConstraintSpec(
        metric="participation_rate", operator=">=", threshold=0.8, percentile=90
    )
    database = tmp_path / "ensemble.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "CREATE TABLE fct_metric_seed_values(ensemble_id VARCHAR, scenario_id VARCHAR, "
            "metric VARCHAR, simulation_year INTEGER, seed INTEGER, value DOUBLE)"
        )
        connection.executemany(
            "INSERT INTO fct_metric_seed_values VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("e1", "s", "participation_rate", 2025, 1, 0.7),
                ("e2", "s", "participation_rate", 2025, 1, 0.99),
            ],
        )
    value, mode = evaluate_constraint_metric(
        requested, {"participation_rate": 0.85}, ensemble_database=database
    )
    assert mode == "point_estimate"
    assert value == 0.85


def test_fixed_percentile_and_compliance_mart_are_supported(tmp_path: Path) -> None:
    ensemble = tmp_path / "ensemble.duckdb"
    with duckdb.connect(str(ensemble)) as connection:
        connection.execute(
            "CREATE TABLE fct_metric_distributions(ensemble_id VARCHAR, scenario_id VARCHAR, metric VARCHAR, simulation_year INTEGER, p90 DOUBLE, is_sufficient BOOLEAN)"
        )
        connection.execute(
            "INSERT INTO fct_metric_distributions VALUES ('e', 's', 'participation_rate', 2025, 0.91, TRUE)"
        )
    constraint = ConstraintSpec(
        metric="participation_rate", operator=">=", threshold=0.8, percentile=90
    )
    assert evaluate_constraint_metric(
        constraint, {"participation_rate": 0.85}, ensemble_database=ensemble
    ) == (0.91, "percentile")

    candidate = tmp_path / "candidate.duckdb"
    with duckdb.connect(str(candidate)) as connection:
        connection.execute(
            "CREATE TABLE fct_workforce_snapshot AS SELECT 2025 AS simulation_year, 'active' AS employment_status"
        )
        connection.execute(
            "CREATE TABLE dq_compliance_monitoring(compliance_status VARCHAR)"
        )
        connection.execute("INSERT INTO dq_compliance_monitoring VALUES ('COMPLIANT')")
    assert extract_point_metrics(candidate)["irs_compliance_pass"] == 1.0
