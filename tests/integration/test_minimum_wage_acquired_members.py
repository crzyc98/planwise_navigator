"""A minimum wage floor covers acquired members (#1253).

Runs the Feature 113 reference simulation on a census where a third of the
rows give a low hourly rate, with a $20 step on 1 July 2026 and four acquired
groups: one joining before the step, one on its date, one later that year and
one the next year at 70% of sampled pay, when no new step is scheduled. The run
is compared with one that shares its census, config, groups and seed but has no
minimum wage.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pytest

from planalign_orchestrator.config import (
    AcquisitionSettings,
    MinimumWageStep,
    SimulationConfig,
)
from tests.fixtures.invariant_simulation import (
    CENSUS_CSV,
    SimulationRun,
    _execute,
    _simulation_config,
    require_successful_run,
)

pytest_plugins = ("tests.fixtures.invariant_simulation",)
pytestmark = [pytest.mark.integration, pytest.mark.multi_year_invariants]

STEP = MinimumWageStep(hourly_rate=20.0, effective_date=date(2026, 7, 1))
HEADCOUNT = 60
GROUPS = (
    AcquisitionSettings(
        id="before", headcount=HEADCOUNT, effective_date=date(2026, 3, 1)
    ),
    AcquisitionSettings(
        id="sameday", headcount=HEADCOUNT, effective_date=STEP.effective_date
    ),
    AcquisitionSettings(
        id="after", headcount=HEADCOUNT, effective_date=date(2026, 10, 1)
    ),
    AcquisitionSettings(
        id="nextyear",
        headcount=HEADCOUNT,
        effective_date=date(2027, 2, 1),
        relative_pay=0.7,
    ),
)
# The date each group's members are raised: the step's date, or the day they
# join when the step is already in force.
RAISED_ON = {
    "before": STEP.effective_date,
    "sameday": STEP.effective_date,
    "after": date(2026, 10, 1),
    "nextyear": date(2027, 2, 1),
}
# A rate from cent-rounded pay can sit a hair under the minimum.
RATE_TOLERANCE = 1e-6
# Rows 1, 4, 7, ... give a low hourly rate; rows 2, 5, ... give $30; the rest
# give neither a rate nor weekly hours, so they have no rate.
CENSUS_SQL = """
    COPY (
      SELECT * REPLACE (
          CASE WHEN rn % 3 = 0 THEN NULL ELSE scheduled_hours_per_week END
            AS scheduled_hours_per_week),
        CASE WHEN rn % 3 = 1 THEN 16.0 + rn % 7 WHEN rn % 3 = 2 THEN 30.0 END
          AS hourly_rate
      FROM (
        SELECT *, ROW_NUMBER() OVER (ORDER BY employee_id) AS rn
        FROM read_csv('{source}')
      )
    ) TO '{target}' (FORMAT PARQUET)
"""
MEMBER_FLOORS = """
    SELECT h.acquisition_id, e.employee_id, e.effective_date::DATE,
      e.previous_compensation, e.compensation_amount, h.compensation_amount,
      r.census_hourly_rate, r.census_annual_pay
    FROM fct_yearly_events e
    JOIN fct_yearly_events h
      ON h.employee_id = e.employee_id AND h.event_type = 'hire'
    LEFT JOIN int_acquired_member_hourly_rates r ON r.employee_id = e.employee_id
    WHERE e.event_type = 'minimum_wage' AND starts_with(e.employee_id, 'ACQ_')
"""
OTHER_EVENTS = """
    SELECT simulation_year, employee_id, event_type, effective_date,
      compensation_amount, previous_compensation, level_id
    FROM fct_yearly_events
    WHERE NOT starts_with(employee_id, 'ACQ_')
      AND employee_id NOT IN ({floored})
    ORDER BY ALL
"""
FLOORED = "SELECT DISTINCT employee_id FROM fct_yearly_events WHERE event_type = 'minimum_wage'"


def _rows(
    database: Path, sql: str, attach: Path | None = None
) -> list[tuple[Any, ...]]:
    with duckdb.connect(str(database), read_only=True) as connection:
        if attach is not None:
            connection.execute(f"ATTACH '{attach}' AS floor (READ_ONLY)")
        return connection.execute(sql).fetchall()


def _run(
    tmp_path_factory: pytest.TempPathFactory, census: Path, name: str, *, floor: bool
) -> SimulationRun:
    payload = _simulation_config(census).model_dump()
    payload["workforce"]["acquisitions"] = [group.model_dump() for group in GROUPS]
    if floor:
        payload["compensation"]["minimum_wage"] = [STEP.model_dump()]
    config = SimulationConfig.model_validate(payload)
    database = tmp_path_factory.mktemp(name) / f"{name}.duckdb"
    return _execute(database, census, config)


@pytest.fixture(scope="module")
def runs(
    tmp_path_factory: pytest.TempPathFactory,
    shared_dev_db_signature: tuple[int, str] | None,
) -> dict[str, SimulationRun]:
    del shared_dev_db_signature
    census = tmp_path_factory.mktemp("hourly-census") / "census.parquet"
    with duckdb.connect() as connection:
        connection.execute(CENSUS_SQL.format(source=CENSUS_CSV, target=census))
    return {
        name: _run(tmp_path_factory, census, name, floor=name == "floor")
        for name in ("groups_only", "floor")
    }


@pytest.fixture(scope="module")
def dbs(runs: dict[str, SimulationRun]) -> dict[str, Path]:
    return {name: require_successful_run(run) for name, run in runs.items()}


def test_both_runs_complete(runs: dict[str, SimulationRun]) -> None:
    for name, run in runs.items():
        assert run.error is None, f"{name}: {run.error!r}"


def test_members_are_raised_on_the_right_date(dbs: dict[str, Path]) -> None:
    floors = _rows(dbs["floor"], MEMBER_FLOORS)
    for group, raised_on in RAISED_ON.items():
        dates = {row[2] for row in floors if row[0] == group}
        assert dates == {raised_on}, group


def test_members_are_raised_from_joining_pay_to_the_minimum(
    dbs: dict[str, Path],
) -> None:
    floors = _rows(dbs["floor"], MEMBER_FLOORS)
    assert floors
    for _, _, _, before, after, joining_pay, rate, rate_pay in floors:
        assert before == pytest.approx(joining_pay, abs=0.005)
        assert rate * before / rate_pay < STEP.hourly_rate
        # The minimum at the member's hours: minimum x pay / rate.
        assert after == pytest.approx(STEP.hourly_rate * rate_pay / rate, abs=0.01)


def test_members_take_their_donors_rate(dbs: dict[str, Path]) -> None:
    rows = _rows(
        dbs["floor"],
        """
        SELECT m.acquisition_id,
          COUNT(*),
          COUNT(*) FILTER (WHERE COALESCE(b.census_hourly_rate, d.census_hourly_rate)
              = m.census_hourly_rate
            AND COALESCE(b.current_compensation, d.census_annual_pay)
              = m.census_annual_pay)
        FROM int_acquired_member_hourly_rates m
        LEFT JOIN int_baseline_workforce b ON b.employee_id = m.donor_employee_id
        LEFT JOIN int_acquired_member_hourly_rates d
          ON d.employee_id = m.donor_employee_id
        GROUP BY m.acquisition_id
        """,
    )
    assert {row[0] for row in rows} == set(RAISED_ON)
    for group, members, matching in rows:
        assert 0 < members < HEADCOUNT, group
        assert matching == members, group


def test_members_without_a_rate_are_not_raised_and_are_counted(
    dbs: dict[str, Path],
) -> None:
    raised_without_rate = _rows(
        dbs["floor"],
        """
        SELECT COUNT(*) FROM fct_yearly_events e
        WHERE e.event_type = 'minimum_wage' AND starts_with(e.employee_id, 'ACQ_')
          AND e.employee_id NOT IN (
            SELECT employee_id FROM int_acquired_member_hourly_rates)
        """,
    )[0][0]
    assert raised_without_rate == 0
    year = STEP.effective_date.year
    counted = _rows(
        dbs["floor"],
        f"""
        WITH members AS (
          SELECT h.employee_id, r.employee_id IS NOT NULL AS has_rate
          FROM fct_yearly_events h
          LEFT JOIN int_acquired_member_hourly_rates r USING (employee_id)
          LEFT JOIN fct_yearly_events t
            ON t.employee_id = h.employee_id AND t.event_type = 'termination'
            AND t.simulation_year = {year}
            AND t.effective_date < DATE '{STEP.effective_date}'
          WHERE h.event_type = 'hire' AND h.acquisition_id IS NOT NULL
            AND h.simulation_year = {year} AND t.employee_id IS NULL
        ),
        census AS (
          SELECT COUNT(*) AS with_rate
          FROM fct_workforce_snapshot s
          JOIN int_baseline_workforce b USING (employee_id)
          LEFT JOIN fct_yearly_events t
            ON t.employee_id = s.employee_id AND t.event_type = 'termination'
            AND t.simulation_year = {year}
            AND t.effective_date < DATE '{STEP.effective_date}'
          WHERE s.simulation_year = {year - 1} AND s.employment_status = 'active'
            AND b.census_hourly_rate IS NOT NULL AND t.employee_id IS NULL
        )
        SELECT
          (SELECT with_rate FROM census) + COUNT(*) FILTER (WHERE has_rate),
          COUNT(*) FILTER (WHERE NOT has_rate),
          (SELECT COUNT(*) FROM fct_yearly_events
            WHERE event_type = 'minimum_wage' AND simulation_year = {year})
        FROM members
        """,
    )[0]
    step = _rows(
        dbs["floor"],
        f"""
        SELECT people_with_rate, people_not_covered, people_raised
        FROM fct_minimum_wage_steps WHERE simulation_year = {year}
        """,
    )[0]
    assert counted[1] > 0
    assert step[0] == counted[0]
    # Simulated hires on the date are not covered either.
    assert step[1] > counted[1]
    assert step[2] == counted[2]


def test_no_member_with_a_rate_ends_a_year_below_the_minimum(
    dbs: dict[str, Path],
) -> None:
    below, members = _rows(
        dbs["floor"],
        f"""
        SELECT COUNT(*) FILTER (WHERE r.census_hourly_rate * s.current_compensation
            / r.census_annual_pay < {STEP.hourly_rate} * (1 - {RATE_TOLERANCE})),
          COUNT(*)
        FROM fct_workforce_snapshot s
        JOIN int_acquired_member_hourly_rates r USING (employee_id)
        WHERE s.simulation_year >= {STEP.effective_date.year}
          AND s.employment_status = 'active'
        """,
    )[0]
    assert below == 0
    assert members > 0


def test_join_year_pay_is_earned_at_each_rate_for_its_days(
    dbs: dict[str, Path],
) -> None:
    rows = _rows(
        dbs["floor"],
        """
        SELECT e.previous_compensation, e.compensation_amount,
          s.current_compensation, s.prorated_annual_compensation
        FROM fct_yearly_events e
        JOIN fct_workforce_snapshot s
          ON s.employee_id = e.employee_id AND s.simulation_year = e.simulation_year
        WHERE e.event_type = 'minimum_wage'
          AND starts_with(e.employee_id, 'ACQ_before_')
          AND s.employment_status = 'active'
        """,
    )
    assert rows
    joined, raised = GROUPS[0].effective_date, STEP.effective_date
    days_before = (raised - joined).days
    days_after = (date(raised.year, 12, 31) - raised).days + 1
    for before, after, year_end, earned in rows:
        assert year_end == pytest.approx(after, abs=0.005)
        expected = (before * days_before + after * days_after) / 365
        assert earned == pytest.approx(expected, abs=0.02)


def test_everyone_not_raised_is_unchanged_through_the_step_year(
    dbs: dict[str, Path],
) -> None:
    sql = OTHER_EVENTS.format(floored=FLOORED.replace("fct_", "floor.fct_"))
    sql = sql.replace(
        "ORDER BY ALL",
        f"AND simulation_year <= {STEP.effective_date.year} ORDER BY ALL",
    )
    baseline = _rows(dbs["groups_only"], sql, attach=dbs["floor"])
    floored_run = _rows(
        dbs["floor"],
        sql.replace("floor.fct_", "fct_"),
    )
    assert baseline
    assert floored_run == baseline
