"""Isolated multi-year regressions for employer eligibility service credit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import duckdb
import pytest

from tests.fixtures.edge_config_matrix import SHARED_DEV_DB, file_signature
from tests.fixtures.employer_eligibility_tenure import (
    BASELINE_CHARACTERIZATION,
    prepare_census_parquet,
    run_termination_rate_case,
    run_wait_case,
)

pytestmark = [pytest.mark.integration, pytest.mark.very_slow]
YEARS = tuple(range(2025, 2030))


def _query(database: Path, sql: str) -> list[tuple]:
    with duckdb.connect(str(database), read_only=True) as connection:
        return connection.execute(sql).fetchall()


def _annual_aggregates(database: Path) -> dict[int, tuple[float, int, float, int]]:
    rows = _query(
        database,
        """
        SELECT
          simulation_year,
          ROUND(SUM(employer_core_amount), 2),
          COUNT_IF(employer_core_amount > 0),
          ROUND(SUM(employer_match_amount), 2),
          COUNT_IF(employer_match_amount > 0)
        FROM fct_workforce_snapshot
        GROUP BY simulation_year
        ORDER BY simulation_year
        """,
    )
    return {
        year: (float(core), core_paid, float(match), match_paid)
        for year, core, core_paid, match, match_paid in rows
    }


@pytest.fixture(scope="session")
def service_census(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("service_credit_census") / "census.parquet"
    return prepare_census_parquet(path)


@pytest.fixture(scope="session")
def service_wait_databases(
    tmp_path_factory: pytest.TempPathFactory,
    service_census: Path,
    shared_dev_database_guard: tuple[int, str] | None,
) -> dict[int, Path]:
    databases = {}
    for wait in range(4):
        database = tmp_path_factory.mktemp(f"service_wait_{wait}") / "simulation.duckdb"
        databases[wait] = run_wait_case(wait, database, service_census)
    assert file_signature(SHARED_DEV_DB) == shared_dev_database_guard
    return databases


@pytest.fixture(scope="session")
def termination_rate_database(
    tmp_path_factory: pytest.TempPathFactory,
    service_census: Path,
    shared_dev_database_guard: tuple[int, str] | None,
) -> Iterator[Path]:
    database = tmp_path_factory.mktemp("service_termination") / "simulation.duckdb"
    yield run_termination_rate_case(database, service_census)
    assert file_signature(SHARED_DEV_DB) == shared_dev_database_guard


def test_opening_year_and_zero_wait_match_characterization(
    service_wait_databases: dict[int, Path],
) -> None:
    baseline = json.loads(BASELINE_CHARACTERIZATION.read_text())
    for wait in (1, 2, 3):
        actual = _annual_aggregates(service_wait_databases[wait])[2025]
        expected = baseline["opening_year"][str(wait)]
        assert actual == pytest.approx(
            (
                expected["core_cost"],
                expected["core_paid"],
                expected["match_cost"],
                expected["match_paid"],
            ),
            abs=0.01,
        )

    actual_zero = _annual_aggregates(service_wait_databases[0])
    for year in YEARS:
        expected = baseline["zero_wait_all_years"][str(year)]
        assert actual_zero[year] == pytest.approx(
            (
                expected["core_cost"],
                expected["core_paid"],
                expected["match_cost"],
                expected["match_paid"],
            ),
            abs=0.01,
        )


def test_core_waits_separate_costs_and_populations_each_year(
    service_wait_databases: dict[int, Path],
) -> None:
    one = _annual_aggregates(service_wait_databases[1])
    two = _annual_aggregates(service_wait_databases[2])
    three = _annual_aggregates(service_wait_databases[3])
    for year in YEARS:
        assert one[year][0] != two[year][0]
        assert three[year][1] < two[year][1]


@pytest.mark.parametrize("wait", [1, 2, 3])
def test_no_below_threshold_awards_and_boundary_is_non_vacuous(
    service_wait_databases: dict[int, Path], wait: int
) -> None:
    violations = _query(
        service_wait_databases[wait],
        f"""
        SELECT employee_id, simulation_year, current_tenure,
               employer_core_amount, employer_match_amount
        FROM fct_workforce_snapshot
        WHERE current_tenure < {wait}
          AND (employer_core_amount > 0 OR employer_match_amount > 0)
        """,
    )
    assert violations == []
    boundary_count = _query(
        service_wait_databases[wait],
        f"""
        SELECT COUNT(*)
        FROM fct_workforce_snapshot
        WHERE current_tenure = {wait - 1}
          AND current_compensation > 0
        """,
    )[0][0]
    assert boundary_count > 0


def test_enforced_match_waits_and_core_use_same_qualification(
    service_wait_databases: dict[int, Path],
) -> None:
    for wait in (2, 3):
        database = service_wait_databases[wait]
        mismatch = _query(
            database,
            """
            SELECT employee_id
            FROM int_employer_eligibility
            WHERE eligible_for_core IS DISTINCT FROM eligible_for_match
            """,
        )
        assert mismatch == []
        assert _annual_aggregates(database)[2029][3] > 0


def test_final_year_eligibility_service_matches_workforce(
    service_wait_databases: dict[int, Path],
) -> None:
    violations = _query(
        service_wait_databases[2],
        """
        SELECT eligibility.employee_id
        FROM int_employer_eligibility eligibility
        INNER JOIN int_workforce_state_accumulator workforce
          ON eligibility.employee_id = workforce.employee_id
         AND eligibility.simulation_year = workforce.simulation_year
         AND workforce.scenario_id = 'service_wait_2'
         AND workforce.plan_design_id = 'service_credit_plan'
        WHERE eligibility.current_tenure IS DISTINCT FROM workforce.current_tenure
        """,
    )
    assert violations == []


def test_allowed_terminations_use_termination_date_service_for_rates(
    termination_rate_database: Path,
) -> None:
    core_violations = _query(
        termination_rate_database,
        """
        SELECT core.employee_id
        FROM int_employer_core_contributions core
        INNER JOIN int_workforce_state_accumulator workforce
          ON core.employee_id = workforce.employee_id
         AND core.simulation_year = workforce.simulation_year
        WHERE workforce.detailed_status_code = 'experienced_termination'
          AND core.employer_core_amount > 0
          AND (
            core.applied_years_of_service IS DISTINCT FROM FLOOR(workforce.current_tenure)
            OR core.core_contribution_rate IS DISTINCT FROM
              CASE WHEN FLOOR(workforce.current_tenure) >= 5 THEN 0.06 ELSE 0.03 END
          )
        """,
    )
    match_violations = _query(
        termination_rate_database,
        """
        SELECT match.employee_id
        FROM int_employee_match_calculations match
        INNER JOIN int_workforce_state_accumulator workforce
          ON match.employee_id = workforce.employee_id
         AND match.simulation_year = workforce.simulation_year
        WHERE workforce.detailed_status_code = 'experienced_termination'
          AND match.employer_match_amount > 0
          AND match.applied_years_of_service IS DISTINCT FROM FLOOR(workforce.current_tenure)
        """,
    )
    contributing_terminations = _query(
        termination_rate_database,
        """
        SELECT COUNT(*)
        FROM int_employer_core_contributions core
        INNER JOIN int_workforce_state_accumulator workforce
          ON core.employee_id = workforce.employee_id
         AND core.simulation_year = workforce.simulation_year
        WHERE workforce.detailed_status_code = 'experienced_termination'
          AND core.employer_core_amount > 0
        """,
    )[0][0]
    assert contributing_terminations > 0
    assert core_violations == []
    assert match_violations == []
