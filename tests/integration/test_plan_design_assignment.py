"""Multi-year acceptance coverage for sticky employee plan-design assignment."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from planalign_orchestrator import ConstructionSpec, build_orchestrator
from planalign_orchestrator.config import PlanDesignAssignmentSettings
from tests.fixtures.invariant_simulation import (
    CENSUS_CSV,
    _database_environment,
    _simulation_config,
)

pytest_plugins = ("tests.fixtures.invariant_simulation",)
pytestmark = [pytest.mark.integration, pytest.mark.multi_year_invariants]


@pytest.fixture(scope="module")
def multi_design_database(
    tmp_path_factory: pytest.TempPathFactory,
    invariant_census_parquet: Path,
) -> Path:
    database = tmp_path_factory.mktemp("plan-design-assignment") / "multi_design.duckdb"
    config = _simulation_config(invariant_census_parquet)
    config.plan_design_assignment = PlanDesignAssignmentSettings.model_validate(
        {
            "default_plan_design_id": "legacy_design",
            "rules": [
                {
                    "type": "hire_date_cutoff",
                    "cutoff": "2015-01-01",
                    "plan_design_id": "current_design",
                }
            ],
        }
    )
    with _database_environment(database):
        orchestrator = build_orchestrator(
            ConstructionSpec(
                config=config,
                database=database,
                threads=1,
                entry_point="invariant_test",
                validation_mode=True,
            )
        ).orchestrator
        orchestrator.execute_multi_year_simulation(start_year=2025, end_year=2027)
    return database


def test_each_employee_has_one_sticky_design(multi_design_database: Path) -> None:
    with duckdb.connect(str(multi_design_database), read_only=True) as connection:
        design_set = connection.execute(
            "SELECT LIST(DISTINCT plan_design_id ORDER BY plan_design_id) "
            "FROM int_plan_design_assignment_accumulator"
        ).fetchone()[0]
        duplicates = connection.execute(
            "SELECT COUNT(*) FROM ("
            " SELECT scenario_id, employee_id, simulation_year"
            " FROM int_plan_design_assignment_accumulator"
            " GROUP BY ALL HAVING COUNT(*) <> 1)"
        ).fetchone()[0]
        reassignments = connection.execute(
            "SELECT COUNT(*) FROM ("
            " SELECT employee_id FROM int_plan_design_assignment_accumulator"
            " GROUP BY employee_id HAVING COUNT(DISTINCT plan_design_id) <> 1)"
        ).fetchone()[0]
    assert design_set == ["current_design", "legacy_design"]
    assert duplicates == 0
    assert reassignments == 0


def test_new_hires_are_assigned_at_hire_time(multi_design_database: Path) -> None:
    with duckdb.connect(str(multi_design_database), read_only=True) as connection:
        violations = connection.execute(
            "SELECT COUNT(*) FROM fct_yearly_events event "
            "JOIN int_plan_design_assignment_accumulator assignment USING "
            "(scenario_id, employee_id, simulation_year) "
            "WHERE event.event_type = 'hire' AND ("
            " assignment.first_assignment_year <> event.simulation_year"
            " OR assignment.plan_design_id <> 'current_design')"
        ).fetchone()[0]
    assert violations == 0


def test_events_and_snapshots_use_canonical_assignment(
    multi_design_database: Path,
) -> None:
    with duckdb.connect(str(multi_design_database), read_only=True) as connection:
        event_mismatches = connection.execute(
            "SELECT COUNT(*) FROM fct_yearly_events event "
            "JOIN int_plan_design_assignment_accumulator assignment USING "
            "(scenario_id, employee_id, simulation_year) "
            "WHERE event.plan_design_id <> assignment.plan_design_id"
        ).fetchone()[0]
        snapshot_mismatches = connection.execute(
            "SELECT COUNT(*) FROM fct_workforce_snapshot snapshot "
            "JOIN int_plan_design_assignment_accumulator assignment USING "
            "(scenario_id, employee_id, simulation_year) "
            "WHERE snapshot.plan_design_id <> assignment.plan_design_id"
        ).fetchone()[0]
    assert event_mismatches == 0
    assert snapshot_mismatches == 0


@pytest.mark.parametrize("census_size", [40, 149])
def test_single_design_is_row_identical_to_legacy_pipeline(
    tmp_path: Path,
    census_size: int,
) -> None:
    census = tmp_path / f"census_{census_size}.parquet"
    with duckdb.connect() as connection:
        connection.read_csv(str(CENSUS_CSV)).limit(census_size).write_parquet(
            str(census)
        )

    databases: list[Path] = []
    for mode in ("legacy", "assignment"):
        database = tmp_path / f"{mode}_{census_size}.duckdb"
        config = _simulation_config(census)
        config.simulation.end_year = 2026
        if mode == "assignment":
            config.plan_design_assignment = PlanDesignAssignmentSettings(
                default_plan_design_id=config.plan_design_id or "default"
            )
        with _database_environment(database):
            build_orchestrator(
                ConstructionSpec(
                    config=config,
                    database=database,
                    threads=1,
                    entry_point="invariant_test",
                    validation_mode=True,
                )
            ).orchestrator.execute_multi_year_simulation(start_year=2025, end_year=2026)
        databases.append(database)

    with duckdb.connect(str(databases[0]), read_only=True) as connection:
        connection.execute(f"ATTACH '{databases[1]}' AS candidate (READ_ONLY)")
        for table, excluded in (
            ("fct_yearly_events", "created_at"),
            ("fct_workforce_snapshot", "snapshot_created_at"),
        ):
            legacy_only, candidate_only = connection.execute(
                f"SELECT "
                f"(SELECT COUNT(*) FROM (SELECT * EXCLUDE ({excluded}) FROM main.{table} "
                f"EXCEPT ALL SELECT * EXCLUDE ({excluded}) FROM candidate.{table})), "
                f"(SELECT COUNT(*) FROM (SELECT * EXCLUDE ({excluded}) FROM candidate.{table} "
                f"EXCEPT ALL SELECT * EXCLUDE ({excluded}) FROM main.{table}))"
            ).fetchone()
            assert (legacy_only, candidate_only) == (0, 0), table
