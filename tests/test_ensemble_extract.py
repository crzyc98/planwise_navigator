"""Fast, isolated-DB tests for read-only per-seed metric extraction."""

from __future__ import annotations

import duckdb
import pytest

from planalign_ensemble.extract import extract_seed_metrics
from planalign_ensemble.models import (
    CANONICAL_METRICS,
    METRIC_REGISTRY,
    SeedRunOutcome,
)


def _write_snapshot(path, *, include_plan_cost: bool = True) -> None:
    """Create a minimal snapshot fixture with two active employees and one exit."""
    plan_cost_column = (
        ", total_employer_contributions DOUBLE" if include_plan_cost else ""
    )
    plan_cost_values = ", 15.0" if include_plan_cost else ""
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            "CREATE TABLE fct_workforce_snapshot ("
            "simulation_year INTEGER, employment_status VARCHAR, "
            "prorated_annual_compensation DOUBLE, employer_match_amount DOUBLE, "
            "participation_status VARCHAR, current_deferral_rate DOUBLE"
            f"{plan_cost_column})"
        )
        conn.execute(
            "INSERT INTO fct_workforce_snapshot VALUES "
            "(2027, 'active', 100.0, 4.0, 'participating', 0.06"
            f"{plan_cost_values}), "
            "(2027, 'active', 200.0, 6.0, 'not_participating', 0.00"
            f"{plan_cost_values}), "
            "(2027, 'terminated', 50.0, 2.0, 'not_participating', 0.00"
            f"{plan_cost_values})"
        )


@pytest.mark.fast
def test_extracts_six_headline_metrics_from_a_completed_seed(tmp_path) -> None:
    """Extraction reuses snapshot definitions and never mutates the source DB."""
    database = tmp_path / "seed_42.duckdb"
    _write_snapshot(database)
    outcome = SeedRunOutcome(seed=42, db_path=database, status="completed")

    values = extract_seed_metrics(outcome, ensemble_id="ens", scenario_id="baseline")
    actual = {value.metric: value.value for value in values}

    assert actual == {
        "active_headcount": 2.0,
        "total_compensation": 350.0,
        "employer_match_cost": 12.0,
        "total_employer_plan_cost": 45.0,
        "participation_rate": pytest.approx(1 / 3),
        "avg_deferral_rate": pytest.approx(0.02),
    }


@pytest.mark.fast
def test_absent_metric_is_preserved_as_null_not_zero(tmp_path) -> None:
    """An unavailable snapshot column must remain distinguishable from $0."""
    database = tmp_path / "seed_42.duckdb"
    _write_snapshot(database, include_plan_cost=False)
    outcome = SeedRunOutcome(seed=42, db_path=database, status="completed")

    values = extract_seed_metrics(outcome, ensemble_id="ens", scenario_id="baseline")
    actual = {value.metric: value.value for value in values}

    assert actual["total_employer_plan_cost"] is None


@pytest.mark.fast
def test_canonical_metric_registry_is_stable_and_complete() -> None:
    assert tuple(METRIC_REGISTRY) == CANONICAL_METRICS
    assert METRIC_REGISTRY["active_headcount"].label == "Active headcount"
    assert METRIC_REGISTRY["total_employer_plan_cost"].source_column == (
        "total_employer_contributions"
    )
    assert METRIC_REGISTRY["participation_rate"].required_columns == (
        "employee_id",
        "simulation_year",
        "participation_status",
    )
    assert METRIC_REGISTRY["avg_deferral_rate"].null_excludes_population is True
