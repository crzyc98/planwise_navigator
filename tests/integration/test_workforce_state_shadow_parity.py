"""Env-driven full-scale shadow comparison for canonical workforce state."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pytest

pytestmark = pytest.mark.integration

WORKFORCE_COLUMNS = (
    "employee_ssn",
    "employee_birth_date",
    "employee_hire_date",
    "termination_date",
    "termination_reason",
    "employment_status",
    "detailed_status_code",
    "current_compensation",
    "prorated_annual_compensation",
    "full_year_equivalent_compensation",
    "current_age",
    "current_tenure",
    "level_id",
    "age_band",
    "tenure_band",
)


def _shadow_database() -> Path:
    value = os.environ.get("F122_SHADOW_DB")
    if not value:
        pytest.skip("F122_SHADOW_DB is not configured")
    path = Path(value)
    assert path.is_file()
    return path


def test_shadow_workforce_matches_snapshot_per_column_and_year() -> None:
    with duckdb.connect(str(_shadow_database()), read_only=True) as connection:
        years = [
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT simulation_year "
                "FROM int_workforce_state_accumulator ORDER BY simulation_year"
            ).fetchall()
        ]
        assert years
        for year in years:
            shadow_count, snapshot_count = connection.execute(
                "SELECT "
                "(SELECT COUNT(*) FROM int_workforce_state_accumulator WHERE simulation_year = ?), "
                "(SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?)",
                [year, year],
            ).fetchone()
            assert shadow_count == snapshot_count
            for column in WORKFORCE_COLUMNS:
                differences = connection.execute(
                    f"""SELECT COUNT(*)
                    FROM int_workforce_state_accumulator shadow
                    FULL OUTER JOIN fct_workforce_snapshot snapshot
                      ON shadow.employee_id = snapshot.employee_id
                     AND shadow.simulation_year = snapshot.simulation_year
                    WHERE COALESCE(shadow.simulation_year, snapshot.simulation_year) = ?
                      AND shadow.{column} IS DISTINCT FROM snapshot.{column}
                    """,
                    [year],
                ).fetchone()[0]
                assert differences == 0, f"{year} {column}: {differences} differences"


def test_shadow_preserves_representative_lifecycle_transitions() -> None:
    with duckdb.connect(str(_shadow_database()), read_only=True) as connection:
        mismatches = connection.execute(
            """SELECT COUNT(*)
            FROM int_workforce_state_accumulator shadow
            JOIN fct_yearly_events event
              ON shadow.scenario_id = event.scenario_id
             AND shadow.plan_design_id = event.plan_design_id
             AND shadow.employee_id = event.employee_id
             AND shadow.simulation_year = event.simulation_year
            WHERE (event.event_type = 'termination'
                   AND shadow.employment_status != 'terminated')
               OR (event.event_type = 'hire'
                   AND EXTRACT(YEAR FROM shadow.employee_hire_date)
                       != shadow.simulation_year)
            """
        ).fetchone()[0]
        assert mismatches == 0
