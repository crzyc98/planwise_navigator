"""A minimum wage floor raises census staff below it on a date (#1229).

Runs the Feature 113 reference simulation on a census where a third of the
rows give an hourly rate, a third give weekly hours and a third have neither,
with a mid-year step in 2026 and a 1 January step in 2027. Each floored run is
compared with a run that shares its census, config and seed but has no
minimum wage, once with merit and COLA and once with a raise budget in force.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pytest

from planalign_orchestrator.config import MinimumWageStep, SimulationConfig
from tests.fixtures.invariant_simulation import (
    CENSUS_CSV,
    SimulationRun,
    _execute,
    _simulation_config,
    require_successful_run,
)

pytest_plugins = ("tests.fixtures.invariant_simulation",)
pytestmark = [pytest.mark.integration, pytest.mark.multi_year_invariants]

STEPS = (
    MinimumWageStep(hourly_rate=20.0, effective_date=date(2026, 7, 1)),
    MinimumWageStep(hourly_rate=22.0, effective_date=date(2027, 1, 1)),
)
RAISE_BUDGET = 0.05
# A rate from cent-rounded pay can sit a hair under the minimum.
RATE_TOLERANCE = 1e-6
# Rows 1, 4, 7, ... give a low hourly rate; rows 2, 5, ... give $30; rows 0, 3,
# ... give neither a rate nor weekly hours, so they have no rate.
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
FLOORED = "SELECT DISTINCT employee_id FROM fct_yearly_events WHERE event_type = 'minimum_wage'"
EVENTS = """
    SELECT simulation_year, employee_id, event_type, effective_date,
      compensation_amount, previous_compensation, level_id, event_details
    FROM fct_yearly_events
    WHERE employee_id NOT IN ({floored})
    ORDER BY ALL
"""
SNAPSHOT = """
    SELECT simulation_year, employee_id, employment_status, level_id,
      current_compensation, prorated_annual_compensation,
      prorated_annual_contributions, employer_match_amount, employer_core_amount
    FROM fct_workforce_snapshot
    WHERE employee_id NOT IN ({floored})
    ORDER BY simulation_year, employee_id
"""


def _rows(
    database: Path, sql: str, attach: Path | None = None
) -> list[tuple[Any, ...]]:
    with duckdb.connect(str(database), read_only=True) as connection:
        if attach is not None:
            connection.execute(f"ATTACH '{attach}' AS base (READ_ONLY)")
        return connection.execute(sql).fetchall()


def _close(left: list[tuple[Any, ...]], right: list[tuple[Any, ...]]) -> bool:
    """Row-for-row equality, with floats compared to 1e-6 (main drifts ~1e-13)."""
    if len(left) != len(right):
        return False
    for a, b in zip(left, right):
        for x, y in zip(a, b):
            if isinstance(x, float) and isinstance(y, float):
                if x != pytest.approx(y, rel=1e-9, abs=1e-6):
                    return False
            elif x != y:
                return False
    return True


@pytest.fixture(scope="module")
def hourly_census(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("hourly-census") / "census.parquet"
    with duckdb.connect() as connection:
        connection.execute(CENSUS_SQL.format(source=CENSUS_CSV, target=path))
    return path


def _run(
    tmp_path_factory: pytest.TempPathFactory,
    census: Path,
    name: str,
    *,
    floor: bool,
    budget: bool,
) -> SimulationRun:
    payload = _simulation_config(census).model_dump()
    if budget:
        payload["compensation"]["raise_budget"] = RAISE_BUDGET
    if floor:
        payload["compensation"]["minimum_wage"] = [step.model_dump() for step in STEPS]
    config = SimulationConfig.model_validate(payload)
    database = tmp_path_factory.mktemp(name) / f"{name}.duckdb"
    return _execute(database, census, config)


@pytest.fixture(scope="module")
def runs(
    tmp_path_factory: pytest.TempPathFactory,
    hourly_census: Path,
    shared_dev_db_signature: tuple[int, str] | None,
) -> dict[str, SimulationRun]:
    del shared_dev_db_signature
    return {
        f"{prefix}{kind}": _run(
            tmp_path_factory,
            hourly_census,
            f"{prefix}{kind}",
            floor=kind == "floor",
            budget=bool(prefix),
        )
        for prefix in ("", "budget_")
        for kind in ("baseline", "floor")
    }


@pytest.fixture(scope="module")
def dbs(runs: dict[str, SimulationRun]) -> dict[str, Path]:
    return {name: require_successful_run(run) for name, run in runs.items()}


def test_all_runs_complete(runs: dict[str, SimulationRun]) -> None:
    for name, run in runs.items():
        assert run.error is None, f"{name}: {run.error!r}"


@pytest.mark.parametrize("name", ["floor", "budget_floor"])
def test_no_one_with_a_rate_ends_a_year_below_the_minimum(
    dbs: dict[str, Path], name: str
) -> None:
    for step in STEPS:
        year = step.effective_date.year
        below = _rows(
            dbs[name],
            f"""
            SELECT COUNT(*) FILTER (WHERE b.census_hourly_rate * s.current_compensation
                / b.current_compensation < {step.hourly_rate} * (1 - {RATE_TOLERANCE})),
              COUNT(*)
            FROM fct_workforce_snapshot s
            JOIN int_baseline_workforce b USING (employee_id)
            WHERE s.simulation_year = {year} AND s.employment_status = 'active'
              AND b.census_hourly_rate IS NOT NULL
            """,
        )
        assert below[0][0] == 0
        assert below[0][1] > 0


def _hand_calculated_increases(
    pay_db: Path, rates_db: Path, census: Path, step: MinimumWageStep
) -> dict[str, float]:
    """Each person's increase, from census rates and pay on the date.

    Pay on the date is opening pay with this year's promotion and merit raise
    when dated on or before the step, read from `pay_db` (the run without the
    floor for the first step, the floored run's prior year for the second).
    """
    year = step.effective_date.year
    rows = _rows(
        pay_db,
        f"""
        WITH census AS (
          SELECT employee_id, CAST(hourly_rate AS DOUBLE) AS hourly_rate
          FROM read_parquet('{census}')
          WHERE hourly_rate IS NOT NULL
        ),
        opening AS (
          SELECT employee_id, current_compensation AS pay
          FROM fct_workforce_snapshot
          WHERE simulation_year = {year - 1} AND employment_status = 'active'
        ),
        events AS (
          SELECT employee_id,
            MAX(compensation_amount) FILTER (WHERE event_type = 'promotion') AS promo,
            MAX(compensation_amount / previous_compensation)
              FILTER (WHERE event_type = 'raise') AS merit_ratio,
            MAX(compensation_amount) FILTER (WHERE event_type = 'raise') AS merit,
            MIN(effective_date) FILTER (WHERE event_type = 'termination') AS left_on
          FROM fct_yearly_events
          WHERE simulation_year = {year}
            AND (event_type = 'termination' OR effective_date <= DATE '{step.effective_date}')
          GROUP BY employee_id
        )
        SELECT o.employee_id, c.hourly_rate,
          CASE WHEN e.promo IS NOT NULL AND e.merit IS NOT NULL
              THEN ROUND(e.promo * e.merit_ratio, 2)
            ELSE COALESCE(e.merit, e.promo, o.pay) END AS pay_on_date
        FROM opening o
        JOIN census c USING (employee_id)
        LEFT JOIN events e USING (employee_id)
        WHERE e.left_on IS NULL OR e.left_on >= DATE '{step.effective_date}'
        """,
    )
    census_pay = dict(
        _rows(
            rates_db,
            "SELECT employee_id, current_compensation FROM int_baseline_workforce",
        )
    )
    increases: dict[str, float] = {}
    for employee_id, census_rate, pay in rows:
        rate = census_rate * pay / census_pay[employee_id]
        if rate < step.hourly_rate:
            increase = round(pay * step.hourly_rate / rate, 2) - pay
            if increase >= 0.01:
                increases[employee_id] = increase
    return increases


def _floor_events(database: Path, year: int) -> dict[str, float]:
    return dict(
        _rows(
            database,
            f"""
            SELECT employee_id, compensation_amount - previous_compensation
            FROM fct_yearly_events
            WHERE event_type = 'minimum_wage' AND simulation_year = {year}
            """,
        )
    )


def _step_summary(database: Path, year: int) -> tuple[Any, ...]:
    return _rows(
        database,
        f"""
        SELECT people_raised, people_with_rate, people_without_rate,
          people_not_covered, added_annual_pay
        FROM fct_minimum_wage_steps WHERE simulation_year = {year}
        """,
    )[0]


@pytest.mark.parametrize("prefix", ["", "budget_"])
def test_added_pay_matches_hand_calculation(
    dbs: dict[str, Path], hourly_census: Path, prefix: str
) -> None:
    floored = dbs[f"{prefix}floor"]
    for step, pay_db in zip(STEPS, (dbs[f"{prefix}baseline"], floored)):
        year = step.effective_date.year
        expected = _hand_calculated_increases(pay_db, floored, hourly_census, step)
        actual = _floor_events(floored, year)
        assert expected, f"no one below ${step.hourly_rate} in {year}"
        assert actual.keys() == expected.keys()
        for employee_id, increase in expected.items():
            assert actual[employee_id] == pytest.approx(increase, abs=0.011)
        raised, with_rate, without_rate, not_covered, added = _step_summary(
            floored, year
        )
        assert raised == len(expected)
        assert added == pytest.approx(sum(actual.values()), abs=0.01)
        assert added == pytest.approx(sum(expected.values()), abs=0.011 * raised)
        assert with_rate > raised and without_rate > 0
        if year > 2025:
            assert not_covered > 0


def test_earned_pay_and_contributions_follow_the_floor_from_its_date(
    dbs: dict[str, Path],
) -> None:
    """Earned pay rises by the increase from 1 July, compounded by a later raise.

    For someone active all year with no promotion after the date, the floored
    run earns the increase from 1 July until their merit raise, then the
    increase times (1 + merit rate) to 31 December.
    """
    step = STEPS[0]
    year = step.effective_date.year
    rows = _rows(
        dbs["floor"],
        f"""
        WITH merit AS (
          SELECT employee_id, CAST(effective_date AS DATE) AS merit_date,
            compensation_amount / previous_compensation AS merit_ratio
          FROM fct_yearly_events
          WHERE event_type = 'raise' AND simulation_year = {year}
        )
        SELECT e.compensation_amount - e.previous_compensation,
          COALESCE(DATE_DIFF('day', DATE '{step.effective_date}', m.merit_date), 184),
          COALESCE(m.merit_ratio, 1),
          f.prorated_annual_compensation - b.prorated_annual_compensation,
          f.prorated_annual_contributions - b.prorated_annual_contributions,
          f.employer_match_amount - b.employer_match_amount,
          f.employer_core_amount - b.employer_core_amount
        FROM fct_yearly_events e
        JOIN fct_workforce_snapshot f
          ON f.employee_id = e.employee_id AND f.simulation_year = {year}
        JOIN base.fct_workforce_snapshot b
          ON b.employee_id = e.employee_id AND b.simulation_year = {year}
        LEFT JOIN merit m
          ON m.employee_id = e.employee_id AND m.merit_date > DATE '{step.effective_date}'
        WHERE e.event_type = 'minimum_wage' AND e.simulation_year = {year}
          AND f.employment_status = 'active'
          AND NOT EXISTS (
            SELECT 1 FROM fct_yearly_events later
            WHERE later.employee_id = e.employee_id AND later.simulation_year = {year}
              AND later.event_type = 'promotion'
              AND later.effective_date > e.effective_date)
        """,
        attach=dbs["baseline"],
    )
    assert rows
    for increase, days_before_merit, merit_ratio, earned, *_ in rows:
        days_after = 184 - days_before_merit
        expected = increase * (days_before_merit + merit_ratio * days_after) / 365
        assert earned == pytest.approx(expected, abs=0.02)
    # Deferrals, match and core never fall, and each rises for someone (they
    # stop rising at plan and IRS limits).
    for column in (4, 5, 6):
        assert all(row[column] >= -0.01 for row in rows)
        assert any(row[column] > 0.01 for row in rows)


def test_without_a_raise_budget_only_floored_people_change(
    dbs: dict[str, Path],
) -> None:
    floored = ",".join(f"'{e}'" for (e,) in _rows(dbs["floor"], FLOORED))
    for sql in (EVENTS, SNAPSHOT):
        query = sql.format(floored=floored)
        assert _close(_rows(dbs["floor"], query), _rows(dbs["baseline"], query))


def test_with_a_raise_budget_the_floor_is_outside_it(dbs: dict[str, Path]) -> None:
    """Merit spend is the budget share of eligible pay with or without the floor."""
    spend = """
        SELECT simulation_year,
          SUM(compensation_amount - previous_compensation) / SUM(previous_compensation)
        FROM fct_yearly_events WHERE event_type = 'raise'
        GROUP BY simulation_year ORDER BY simulation_year
    """
    for name in ("budget_baseline", "budget_floor"):
        for _, share in _rows(dbs[name], spend):
            assert share == pytest.approx(RAISE_BUDGET, abs=1e-4)
    first_year = f"""
        SELECT employee_id, event_type, effective_date, compensation_amount
        FROM fct_yearly_events
        WHERE simulation_year <= {STEPS[0].effective_date.year}
          AND event_type <> 'minimum_wage'
        ORDER BY ALL
    """
    assert _close(
        _rows(dbs["budget_floor"], first_year),
        _rows(dbs["budget_baseline"], first_year),
    )
