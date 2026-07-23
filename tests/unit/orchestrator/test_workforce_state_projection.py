"""Contracts for the disposable strict N-1 workforce projection."""

from __future__ import annotations

import duckdb

from planalign_orchestrator.utils import DatabaseConnectionManager
from planalign_orchestrator.workforce_state_projection import (
    WorkforceStateProjection,
)


def _create_accumulator(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """CREATE TABLE int_workforce_state_accumulator (
          scenario_id VARCHAR, plan_design_id VARCHAR, employee_id VARCHAR,
          simulation_year INTEGER, employee_ssn VARCHAR,
          employee_birth_date TIMESTAMP, employee_hire_date TIMESTAMP,
          current_compensation DOUBLE,
          full_year_equivalent_compensation DOUBLE, current_age BIGINT,
          current_tenure INTEGER, level_id INTEGER, employment_status VARCHAR,
          termination_date TIMESTAMP, scheduled_hours_per_week DECIMAL(5, 2)
        )"""
    )


def test_first_year_projection_is_empty_without_accumulator(tmp_path) -> None:
    manager = DatabaseConnectionManager(tmp_path / "first.duckdb")
    try:
        result = WorkforceStateProjection(manager).rebuild(2025)
        assert result.employee_count == 0
        with manager.get_connection() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM workforce_state_projection"
            ).fetchone() == (0,)
    finally:
        manager.close_all()


def test_projection_contains_only_n_minus_one_and_selected_scope(tmp_path) -> None:
    manager = DatabaseConnectionManager(tmp_path / "scope.duckdb")
    try:
        with manager.get_connection() as connection:
            _create_accumulator(connection)
            connection.execute(
                """INSERT INTO int_workforce_state_accumulator VALUES
                ('scenario-a', 'plan-a', 'prior', 2026, '1', TIMESTAMP '1990-01-01', TIMESTAMP '2020-01-01', 100, 101, 36, 6, 2, 'active', NULL, 20),
                ('scenario-a', 'plan-a', 'older', 2025, '2', TIMESTAMP '1990-01-01', TIMESTAMP '2020-01-01', 90, 91, 35, 5, 1, 'active', NULL, NULL),
                ('scenario-b', 'plan-a', 'other', 2026, '3', TIMESTAMP '1990-01-01', TIMESTAMP '2020-01-01', 80, 81, 36, 6, 1, 'active', NULL, NULL),
                ('scenario-a', 'plan-a', 'current', 2027, '4', TIMESTAMP '1990-01-01', TIMESTAMP '2020-01-01', 110, 111, 37, 7, 3, 'active', NULL, NULL)
                """
            )

        projection = WorkforceStateProjection(manager)
        first = projection.rebuild(2027, "scenario-a", "plan-a")
        with manager.get_connection() as connection:
            rows = connection.execute(
                "SELECT employee_id, source_simulation_year, scenario_id, "
                "plan_design_id FROM workforce_state_projection"
            ).fetchall()
        second = projection.rebuild(2027, "scenario-a", "plan-a")

        assert first == second
        assert rows == [("prior", 2026, "scenario-a", "plan-a")]
        assert not manager._pool._in_use
    finally:
        manager.close_all()


def test_projection_rebuild_is_deterministic(tmp_path) -> None:
    manager = DatabaseConnectionManager(tmp_path / "repeat.duckdb")
    try:
        with manager.get_connection() as connection:
            _create_accumulator(connection)
            connection.execute(
                """INSERT INTO int_workforce_state_accumulator VALUES
                ('default', 'default', 'b', 2025, '2', TIMESTAMP '1990-01-01', TIMESTAMP '2020-01-01', 90, 91, 35, 5, 1, 'active', NULL, NULL),
                ('default', 'default', 'a', 2025, '1', TIMESTAMP '1990-01-01', TIMESTAMP '2020-01-01', 100, 101, 35, 5, 2, 'active', NULL, 20)
                """
            )
        projection = WorkforceStateProjection(manager)
        projection.rebuild(2026)
        with manager.get_connection() as connection:
            before = connection.execute(
                "SELECT * FROM workforce_state_projection ORDER BY employee_id"
            ).fetchall()
        projection.rebuild(2026)
        with manager.get_connection() as connection:
            after = connection.execute(
                "SELECT * FROM workforce_state_projection ORDER BY employee_id"
            ).fetchall()
        assert after == before
    finally:
        manager.close_all()
