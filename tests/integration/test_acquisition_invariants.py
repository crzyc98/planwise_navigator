"""An acquired group joins on top of organic hiring (#1226).

Runs the Feature 113 reference simulation again with a mid-year acquisition and
a second one on 1 January of the final year, and compares it with the reference
run that shares its config and seed.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Iterator

import duckdb
import pytest

from planalign_orchestrator.config import AcquisitionSettings
from tests.fixtures.invariant_simulation import (
    SimulationRun,
    _execute,
    _simulation_config,
    require_successful_run,
)

pytest_plugins = ("tests.fixtures.invariant_simulation",)
pytestmark = [pytest.mark.integration, pytest.mark.multi_year_invariants]

JOIN_YEAR = 2026
HEADCOUNT = 60
FINAL_YEAR = 2027
FINAL_HEADCOUNT = 15
EFFECTIVE = date(JOIN_YEAR, 7, 1)
OTHER_EVENTS = """
    SELECT simulation_year, event_type, employee_id, effective_date,
      compensation_amount, level_id, employee_age
    FROM fct_yearly_events
    WHERE NOT starts_with(employee_id, 'ACQ_') AND simulation_year <= {year}
    ORDER BY ALL
"""
ACTIVE_HEADCOUNT = """
    SELECT simulation_year, COUNT(*)
    FROM fct_workforce_snapshot
    WHERE employment_status = 'active'
    GROUP BY simulation_year ORDER BY simulation_year
"""


@pytest.fixture(scope="module")
def acquired_run(
    tmp_path_factory: pytest.TempPathFactory,
    invariant_census_parquet: Path,
    shared_dev_db_signature: tuple[int, str] | None,
) -> Iterator[SimulationRun]:
    del shared_dev_db_signature
    config = _simulation_config(invariant_census_parquet)
    config.workforce.acquisitions = [
        AcquisitionSettings(id="acme", headcount=HEADCOUNT, effective_date=EFFECTIVE),
        AcquisitionSettings(
            id="late", headcount=FINAL_HEADCOUNT, effective_date=date(FINAL_YEAR, 1, 1)
        ),
    ]
    database = tmp_path_factory.mktemp("acquired-run") / "acquired.duckdb"
    yield _execute(database, invariant_census_parquet, config)


@pytest.fixture(scope="module")
def acquired_db(acquired_run: SimulationRun) -> Path:
    return require_successful_run(acquired_run)


def _rows(database: Path, sql: str) -> list[tuple[Any, ...]]:
    with duckdb.connect(str(database), read_only=True) as connection:
        return connection.execute(sql).fetchall()


def test_acquired_simulation_completed(acquired_run: SimulationRun) -> None:
    assert acquired_run.error is None, repr(acquired_run.error)


def test_everyone_else_is_unchanged_through_join_year(
    invariant_run_db: Path, acquired_db: Path
) -> None:
    sql = OTHER_EVENTS.format(year=JOIN_YEAR)
    baseline = _rows(invariant_run_db, sql)
    assert any(row[1] == "hire" for row in baseline)
    assert _rows(acquired_db, sql) == baseline


def test_join_year_headcount_is_baseline_plus_group(
    invariant_run_db: Path, acquired_db: Path
) -> None:
    baseline = dict(_rows(invariant_run_db, ACTIVE_HEADCOUNT))
    acquired = dict(_rows(acquired_db, ACTIVE_HEADCOUNT))
    assert acquired[JOIN_YEAR - 1] == baseline[JOIN_YEAR - 1]
    assert acquired[JOIN_YEAR] == baseline[JOIN_YEAR] + HEADCOUNT


def test_members_join_on_the_date_with_marker(acquired_db: Path) -> None:
    rows = _rows(
        acquired_db,
        f"""
        SELECT e.employee_id, e.effective_date::DATE, s.employee_hire_date::DATE,
          s.acquisition_id, e.employee_tenure, s.current_tenure
        FROM fct_yearly_events e
        JOIN fct_workforce_snapshot s
          ON s.employee_id = e.employee_id AND s.simulation_year = e.simulation_year
        WHERE e.event_type = 'hire' AND e.acquisition_id = 'acme'
          AND e.simulation_year = {JOIN_YEAR}
        """,
    )
    assert len(rows) == HEADCOUNT
    for employee_id, effective, hired, marker, event_tenure, tenure in rows:
        assert employee_id.startswith("ACQ_acme_")
        assert effective == hired == EFFECTIVE
        assert marker == "acme"
        assert event_tenure == tenure


def test_members_have_no_join_year_changes_or_new_hire_turnover(
    acquired_db: Path,
) -> None:
    rows = _rows(
        acquired_db,
        """
        SELECT e.simulation_year, e.event_type, e.event_category
        FROM fct_yearly_events e
        JOIN fct_yearly_events joined
          ON joined.employee_id = e.employee_id AND joined.event_type = 'hire'
        WHERE joined.acquisition_id IS NOT NULL
          AND e.event_type IN ('termination', 'raise', 'promotion')
          AND (e.simulation_year = joined.simulation_year
            OR e.event_category = 'new_hire_termination')
        """,
    )
    assert rows == []


def test_next_year_counts_members_as_experienced(acquired_db: Path) -> None:
    needs = _rows(
        acquired_db,
        f"""
        SELECT starting_workforce_count, starting_experienced_count,
          starting_new_hire_count
        FROM int_workforce_needs WHERE simulation_year = {JOIN_YEAR + 1}
        """,
    )[0]
    organic_survivors = _rows(
        acquired_db,
        f"""
        SELECT COUNT(*) FROM fct_workforce_snapshot
        WHERE simulation_year = {JOIN_YEAR} AND employment_status = 'active'
          AND YEAR(employee_hire_date) = {JOIN_YEAR} AND acquisition_id IS NULL
        """,
    )[0][0]
    assert needs[2] == organic_survivors
    assert needs[0] == needs[1] + needs[2]


def test_member_tenure_advances_from_sampled_value(acquired_db: Path) -> None:
    rows = _rows(
        acquired_db,
        f"""
        SELECT prior.current_tenure, later.current_tenure
        FROM fct_workforce_snapshot prior
        JOIN fct_workforce_snapshot later
          ON later.employee_id = prior.employee_id
         AND later.simulation_year = prior.simulation_year + 1
        WHERE prior.simulation_year = {JOIN_YEAR}
          AND prior.acquisition_id IS NOT NULL
          AND later.employment_status = 'active'
        """,
    )
    assert rows, "expected surviving members in the year after joining"
    assert all(later == prior + 1 for prior, later in rows)
    assert any(prior > 0 for prior, _ in rows), "prior service was not carried"


def test_member_ids_never_collide(acquired_db: Path) -> None:
    duplicates = _rows(
        acquired_db,
        """
        SELECT simulation_year,
          COUNT(*) - COUNT(DISTINCT employee_id),
          COUNT(*) - COUNT(DISTINCT employee_ssn)
        FROM fct_workforce_snapshot
        GROUP BY simulation_year
        HAVING COUNT(*) <> COUNT(DISTINCT employee_id)
          OR COUNT(*) <> COUNT(DISTINCT employee_ssn)
        """,
    )
    assert duplicates == []


def test_second_group_joins_in_final_year_with_its_own_ids(acquired_db: Path) -> None:
    rows = _rows(
        acquired_db,
        f"""
        SELECT COUNT(*), COUNT(DISTINCT employee_id),
          MIN(effective_date)::DATE, MAX(effective_date)::DATE
        FROM fct_yearly_events
        WHERE event_type = 'hire' AND acquisition_id = 'late'
          AND simulation_year = {FINAL_YEAR} AND starts_with(employee_id, 'ACQ_late_')
        """,
    )
    start = date(FINAL_YEAR, 1, 1)
    assert rows == [(FINAL_HEADCOUNT, FINAL_HEADCOUNT, start, start)]
    active = _rows(
        acquired_db,
        f"""
        SELECT COUNT(*) FROM fct_workforce_snapshot
        WHERE simulation_year = {FINAL_YEAR} AND acquisition_id = 'late'
          AND employment_status = 'active'
        """,
    )
    assert active == [(FINAL_HEADCOUNT,)]


def test_terminated_member_keeps_prior_service(acquired_db: Path) -> None:
    rows = _rows(
        acquired_db,
        f"""
        SELECT joined.employee_tenure, left_year.current_tenure,
          left_year.simulation_year - {JOIN_YEAR}
        FROM fct_yearly_events joined
        JOIN fct_workforce_snapshot left_year
          ON left_year.employee_id = joined.employee_id
         AND left_year.employment_status = 'terminated'
        WHERE joined.event_type = 'hire' AND joined.acquisition_id = 'acme'
        """,
    )
    assert rows, "expected at least one member to leave after the join year"
    for joined_tenure, final_tenure, years_later in rows:
        assert (
            joined_tenure + years_later - 1
            <= final_tenure
            <= joined_tenure + years_later
        )
    assert any(joined_tenure > 0 for joined_tenure, _, _ in rows)


def test_members_resemble_the_staff_they_were_drawn_from(acquired_db: Path) -> None:
    unmatched = _rows(
        acquired_db,
        f"""
        SELECT COUNT(*)
        FROM fct_yearly_events member
        WHERE member.event_type = 'hire' AND member.acquisition_id = 'acme'
          AND NOT EXISTS (
            SELECT 1 FROM fct_workforce_snapshot donor
            WHERE donor.simulation_year = {JOIN_YEAR - 1}
              AND donor.employment_status = 'active'
              AND donor.level_id = member.level_id
              AND donor.current_age + 1 = member.employee_age
              AND donor.current_tenure + 1 = member.employee_tenure
              AND donor.full_year_equivalent_compensation = member.compensation_amount
          )
        """,
    )
    assert unmatched == [(0,)]
