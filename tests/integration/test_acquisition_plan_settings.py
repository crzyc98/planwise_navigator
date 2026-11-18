"""DC plan settings for an acquired group (#1227).

Two isolated 2025-2027 runs share one config and seed: a baseline, and the same
scenario with two acquisitions joining on 1 July 2026:

- ``acme`` leaves the plan settings unset: prior service counts, members enter
  on the acquisition date and go through auto-enrollment like new entrants.
- ``beta`` sets the alternatives: service starts on the acquisition date,
  members wait out the plan's 365-day waiting period, and half of them start
  deferring 6%.

The plan is chosen so that service drives every formula: auto-enrollment for
all eligible employees, a points-based core with a one-year eligibility
minimum and a flat 1% below three years of service, and a match graded by
service (50% below three years, 100% from three, on the first 6%).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Iterator

import duckdb
import pytest
import yaml

from planalign_api.models.vesting import VestingScheduleType
from planalign_api.services.vesting_service import get_vesting_percentage
from planalign_orchestrator.config import SimulationConfig, load_simulation_config
from tests.fixtures.invariant_simulation import (
    CONFIG_YAML,
    SimulationRun,
    _execute,
    require_successful_run,
)

pytest_plugins = ("tests.fixtures.invariant_simulation",)
pytestmark = [pytest.mark.integration, pytest.mark.edge_config_matrix]

JOIN_YEAR = 2026
EFFECTIVE = date(JOIN_YEAR, 7, 1)
HEADCOUNT = 40
WAITING_DAYS = 365
PARTICIPATION_RATE = 0.5
DEFERRAL_RATE = 0.06
CORE_BANDS = ((0, 30, 0.01), (30, 50, 0.02), (50, None, 0.03))
CORE_MIN_SERVICE_YEARS = 3
CORE_PRE_SERVICE_RATE = 0.01
MATCH_CAP = 0.06


def _plan_config(census_parquet: Path) -> dict[str, Any]:
    raw = yaml.safe_load(CONFIG_YAML.read_text())
    raw["scenario_id"] = "acquisition_plan_settings"
    raw["setup"]["census_parquet_path"] = str(census_parquet)
    raw["eligibility"] = {"waiting_period_days": WAITING_DAYS}
    raw["employer_core_contribution"] = {
        "enabled": True,
        "status": "points_based",
        "contribution_rate": 0.001,
        "points_schedule": [
            {"min_points": low, "max_points": high, "contribution_rate": rate}
            for low, high, rate in CORE_BANDS
        ],
        "points_min_service_years": CORE_MIN_SERVICE_YEARS,
        "points_pre_service_rate": CORE_PRE_SERVICE_RATE * 100,
        "eligibility": {
            "minimum_tenure_years": 1,
            "require_active_at_year_end": True,
            "minimum_hours_annual": 0,
            "allow_new_hires": False,
        },
    }
    raw["employer_match"] = {
        "apply_eligibility": False,
        "employer_match_status": "tenure_graded",
        "tenure_graded_bands": [
            {
                "min_years": 0,
                "max_years": 3,
                "tiers": [
                    {"employee_min": 0.0, "employee_max": MATCH_CAP, "match_rate": 0.5}
                ],
            },
            {
                "min_years": 3,
                "max_years": None,
                "tiers": [
                    {"employee_min": 0.0, "employee_max": MATCH_CAP, "match_rate": 1.0}
                ],
            },
        ],
    }
    assert raw["enrollment"]["auto_enrollment"]["scope"] == "all_eligible_employees"
    return raw


def _load(raw: dict[str, Any], path: Path) -> SimulationConfig:
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return load_simulation_config(path, env_overrides=False)


@pytest.fixture(scope="module")
def runs(
    tmp_path_factory: pytest.TempPathFactory,
    invariant_census_parquet: Path,
    shared_dev_db_signature: tuple[int, str] | None,
) -> Iterator[tuple[SimulationRun, SimulationRun]]:
    del shared_dev_db_signature
    root = tmp_path_factory.mktemp("acquisition-plan-settings")
    raw = _plan_config(invariant_census_parquet)
    baseline = _execute(
        root / "baseline.duckdb",
        invariant_census_parquet,
        _load(raw, root / "baseline.yaml"),
    )
    raw["workforce"]["acquisitions"] = [
        {"id": "acme", "headcount": HEADCOUNT, "effective_date": EFFECTIVE},
        {
            "id": "beta",
            "headcount": HEADCOUNT,
            "effective_date": EFFECTIVE,
            "service_credit": "acquisition_date",
            "plan_entry": "waiting_period",
            "starting_participation_rate": PARTICIPATION_RATE,
            "starting_deferral_rate": DEFERRAL_RATE,
        },
    ]
    acquired = _execute(
        root / "acquired.duckdb",
        invariant_census_parquet,
        _load(raw, root / "acquired.yaml"),
    )
    yield baseline, acquired


@pytest.fixture(scope="module")
def baseline_db(runs: tuple[SimulationRun, SimulationRun]) -> Path:
    return require_successful_run(runs[0])


@pytest.fixture(scope="module")
def acquired_db(runs: tuple[SimulationRun, SimulationRun]) -> Path:
    return require_successful_run(runs[1])


def _rows(database: Path, sql: str) -> list[tuple[Any, ...]]:
    with duckdb.connect(str(database), read_only=True) as connection:
        return connection.execute(sql).fetchall()


def test_both_runs_completed(runs: tuple[SimulationRun, SimulationRun]) -> None:
    for run in runs:
        assert run.error is None, repr(run.error)


def test_service_credit_sets_current_tenure(acquired_db: Path) -> None:
    rows = _rows(
        acquired_db,
        """
        SELECT s.acquisition_id, s.simulation_year, s.current_tenure,
          e.employee_tenure
        FROM fct_workforce_snapshot s
        JOIN fct_yearly_events e
          ON e.employee_id = s.employee_id AND e.event_type = 'hire'
        WHERE s.acquisition_id IS NOT NULL AND s.employment_status = 'active'
        """,
    )
    assert {row[0] for row in rows} == {"acme", "beta"}
    for acquisition, year, tenure, carried in rows:
        expected = carried if acquisition == "acme" else 0
        assert tenure == expected + (year - JOIN_YEAR)
    acme_carried = [row[3] for row in rows if row[0] == "acme"]
    assert min(acme_carried) >= 1


def test_entry_on_acquisition_date_or_after_waiting_period(acquired_db: Path) -> None:
    rows = _rows(
        acquired_db,
        """
        SELECT regexp_extract(employee_id, '^ACQ_([a-z]+)_', 1),
          simulation_year, effective_date::DATE, COUNT(*)
        FROM fct_yearly_events
        WHERE event_type = 'eligibility' AND starts_with(employee_id, 'ACQ_')
        GROUP BY ALL ORDER BY ALL
        """,
    )
    acme = [row for row in rows if row[0] == "acme"]
    beta = [row for row in rows if row[0] == "beta"]
    assert acme == [("acme", JOIN_YEAR, EFFECTIVE, HEADCOUNT)]
    assert [row[1:3] for row in beta] == [(JOIN_YEAR + 1, date(JOIN_YEAR + 1, 7, 1))]


def test_default_members_auto_enroll_like_new_entrants(acquired_db: Path) -> None:
    rows = _rows(
        acquired_db,
        f"""
        SELECT event_category, MIN(effective_date)::DATE, COUNT(DISTINCT employee_id)
        FROM fct_yearly_events
        WHERE starts_with(employee_id, 'ACQ_acme_') AND event_type = 'enrollment'
          AND simulation_year = {JOIN_YEAR}
        GROUP BY ALL
        """,
    )
    categories = {row[0] for row in rows}
    assert "auto_enrollment" in categories
    assert "acquisition_enrollment" not in categories
    assert min(row[1] for row in rows) >= EFFECTIVE
    # All eligible employees are in auto-enrollment scope, so everyone enrolls.
    assert sum(row[2] for row in rows) == HEADCOUNT


def test_starting_participation_is_exact_and_skips_auto_enrollment(
    acquired_db: Path,
) -> None:
    # Members active at the start of the entry year (no join-year turnover).
    entering = _rows(
        acquired_db,
        f"""
        SELECT COUNT(*) FROM int_workforce_state_accumulator
        WHERE simulation_year = {JOIN_YEAR + 1}
          AND starts_with(employee_id, 'ACQ_beta_')
        """,
    )[0][0]
    rows = _rows(
        acquired_db,
        """
        SELECT simulation_year, event_type, event_category,
          effective_date::DATE, employee_deferral_rate
        FROM fct_yearly_events
        WHERE starts_with(employee_id, 'ACQ_beta_')
          AND event_type IN ('enrollment', 'enrollment_change')
        """,
    )
    assert entering == HEADCOUNT
    joined = [row for row in rows if row[2] == "acquisition_enrollment"]
    survivors_at_entry = _rows(
        acquired_db,
        f"""
        SELECT COUNT(*) FROM fct_yearly_events
        WHERE starts_with(employee_id, 'ACQ_beta_') AND event_type = 'eligibility'
          AND simulation_year = {JOIN_YEAR + 1}
        """,
    )[0][0]
    # The top half of the entering cohort is drawn; any drawn member who left
    # before entering never enrolls.
    target = round(PARTICIPATION_RATE * entering)
    assert target - (entering - survivors_at_entry) <= len(joined) <= target
    assert all(row[0] == JOIN_YEAR + 1 for row in joined)
    assert {row[3] for row in joined} == {date(JOIN_YEAR + 1, 7, 1)}
    assert {float(row[4]) for row in joined} == {DEFERRAL_RATE}
    assert [row for row in rows if row[2] != "acquisition_enrollment"] == []


def _band_rate(points: int) -> float:
    for low, high, rate in CORE_BANDS:
        if points >= low and (high is None or points < high):
            return rate
    raise AssertionError(points)


def test_core_follows_credited_service(acquired_db: Path) -> None:
    rows = _rows(
        acquired_db,
        """
        SELECT s.acquisition_id, s.simulation_year, FLOOR(s.current_age)::INT,
          FLOOR(s.current_tenure)::INT, c.eligible_for_core,
          CAST(c.core_contribution_rate AS DOUBLE), c.applied_years_of_service
        FROM fct_workforce_snapshot s
        JOIN int_employer_core_contributions c
          ON c.employee_id = s.employee_id AND c.simulation_year = s.simulation_year
        WHERE s.acquisition_id IS NOT NULL AND s.employment_status = 'active'
        """,
    )
    assert rows
    for acquisition, year, age, years, eligible, rate, applied in rows:
        assert applied == years
        assert eligible == (years >= 1), (acquisition, year, years)
        if not eligible:
            continue
        expected = (
            CORE_PRE_SERVICE_RATE
            if years < CORE_MIN_SERVICE_YEARS
            else _band_rate(age + years)
        )
        assert rate == pytest.approx(expected)
    beta_join_year = [row for row in rows if row[:2] == ("beta", JOIN_YEAR)]
    assert beta_join_year and not any(row[4] for row in beta_join_year)
    assert any(row[3] >= CORE_MIN_SERVICE_YEARS for row in rows if row[0] == "acme")


def test_tenure_graded_match_follows_credited_service(acquired_db: Path) -> None:
    rows = _rows(
        acquired_db,
        """
        SELECT s.acquisition_id, FLOOR(s.current_tenure)::INT, m.applied_years_of_service,
          m.deferral_rate, LEAST(m.eligible_compensation, m.irs_401a17_limit),
          m.employer_match_amount, m.is_eligible_for_match
        FROM fct_workforce_snapshot s
        JOIN int_employee_match_calculations m
          ON m.employee_id = s.employee_id AND m.simulation_year = s.simulation_year
        WHERE s.acquisition_id IS NOT NULL AND s.employment_status = 'active'
        """,
    )
    paid = 0
    for _, years, applied, deferral, compensation, match, eligible in rows:
        assert applied == years
        # Match eligibility is the plan's hours rule, prorated from the join date.
        rate = (1.0 if years >= 3 else 0.5) if eligible else 0.0
        expected = rate * min(float(deferral or 0), MATCH_CAP) * float(compensation)
        # deferral_rate is stored to 4 dp, so allow half a basis point of slack.
        slack = rate * 0.00005 * float(compensation) + 0.05
        assert float(match) == pytest.approx(expected, abs=slack)
        paid += match > 0
    assert paid > 0
    assert {row[2] >= 3 for row in rows if row[0] == "acme"} == {True, False}


def test_vesting_reads_credited_service(acquired_db: Path) -> None:
    rows = _rows(
        acquired_db,
        f"""
        SELECT acquisition_id, current_tenure FROM fct_workforce_snapshot
        WHERE acquisition_id IS NOT NULL AND simulation_year = {JOIN_YEAR}
        """,
    )
    schedule = VestingScheduleType.GRADED_5_YEAR
    beta = {
        get_vesting_percentage(schedule, tenure)
        for name, tenure in rows
        if name == "beta"
    }
    acme = [
        get_vesting_percentage(schedule, tenure)
        for name, tenure in rows
        if name == "acme"
    ]
    assert beta == {get_vesting_percentage(schedule, 0)}
    assert max(acme) > get_vesting_percentage(schedule, 0)


NON_MEMBER_CONTRIBUTIONS = f"""
    SELECT employee_id, simulation_year, employment_status, current_deferral_rate,
      prorated_annual_contributions, employer_match_amount, employer_core_amount
    FROM fct_workforce_snapshot
    WHERE acquisition_id IS NULL AND simulation_year <= {JOIN_YEAR}
    ORDER BY employee_id, simulation_year
"""


def test_non_members_contributions_match_a_run_without_the_acquisition(
    baseline_db: Path, acquired_db: Path
) -> None:
    baseline = _rows(baseline_db, NON_MEMBER_CONTRIBUTIONS)
    acquired = _rows(acquired_db, NON_MEMBER_CONTRIBUTIONS)
    assert [row[:3] for row in acquired] == [row[:3] for row in baseline]
    assert any(row[5] for row in baseline) and any(row[6] for row in baseline)
    for left, right in zip(baseline, acquired):
        for a, b in zip(left[3:], right[3:]):
            assert (a is None) == (b is None), left[0]
            if a is not None:
                assert float(a) == pytest.approx(float(b), abs=1e-6), left[0]
