"""Net employer cost: cumulative basis, policy semantics, timing (issue #444)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from planalign_api.models.employer_cost import ForfeiturePolicy
from planalign_api.models.vesting import (
    ForfeitureYearRow,
    VestingScheduleConfig,
    VestingScheduleType,
)
from planalign_api.services.employer_cost_service import (
    build_employer_cost_offsets,
    build_employer_cost_series,
    compute_employer_cost,
    query_gross_employer_cost,
)
from planalign_api.services.vesting_service import project_forfeitures_for_connection

pytestmark = [pytest.mark.fast]

SNAPSHOT_DDL = """
    CREATE TABLE fct_workforce_snapshot (
        employee_id VARCHAR,
        simulation_year INTEGER,
        employment_status VARCHAR,
        employee_hire_date DATE,
        termination_date DATE,
        current_tenure INTEGER,
        tenure_band VARCHAR,
        annual_hours_worked INTEGER,
        employer_match_amount DOUBLE,
        employer_core_amount DOUBLE,
        total_employer_contributions DOUBLE,
        prorated_annual_compensation DOUBLE
    )
"""

# 'cliff' accrues $1,000 of employer money in each of 2025, 2026 and 2027 and
# terminates in 2028 at tenure 3. Under a 3-year cliff that is 100% vested; the
# interesting case is the 4-year cliff, where all $3,000 is forfeited.
# 'stayer' is present throughout so every year has gross cost and compensation.
ROWS = """
    INSERT INTO fct_workforce_snapshot VALUES
        ('cliff',  2025, 'ACTIVE',     DATE '2024-01-01', NULL,              1, '<2',  2080,  700.0, 300.0, 1000.0, 100000.0),
        ('stayer', 2025, 'ACTIVE',     DATE '2015-01-01', NULL,             10, '10-19', 2080, 1400.0, 600.0, 2000.0, 200000.0),
        ('cliff',  2026, 'ACTIVE',     DATE '2024-01-01', NULL,              2, '2-4', 2080,  700.0, 300.0, 1000.0, 100000.0),
        ('stayer', 2026, 'ACTIVE',     DATE '2015-01-01', NULL,             11, '10-19', 2080, 1400.0, 600.0, 2000.0, 200000.0),
        ('cliff',  2027, 'ACTIVE',     DATE '2024-01-01', NULL,              3, '2-4', 2080,  700.0, 300.0, 1000.0, 100000.0),
        ('stayer', 2027, 'ACTIVE',     DATE '2015-01-01', NULL,             12, '10-19', 2080, 1400.0, 600.0, 2000.0, 200000.0),
        ('cliff',  2028, 'TERMINATED', DATE '2024-01-01', DATE '2028-06-30', 3, '2-4', 1040,    0.0,   0.0,    0.0,  50000.0),
        ('stayer', 2028, 'ACTIVE',     DATE '2015-01-01', NULL,             13, '10-19', 2080, 1400.0, 600.0, 2000.0, 200000.0),
        ('stayer', 2029, 'ACTIVE',     DATE '2015-01-01', NULL,             14, '10-19', 2080, 1400.0, 600.0, 2000.0, 200000.0)
"""


@pytest.fixture
def scenario_db(tmp_path: Path) -> Path:
    path = tmp_path / "scenario.duckdb"
    conn = duckdb.connect(str(path))
    try:
        conn.execute(SNAPSHOT_DDL)
        conn.execute(ROWS)
    finally:
        conn.close()
    return path


def _schedule(schedule_type: VestingScheduleType, name: str) -> VestingScheduleConfig:
    return VestingScheduleConfig(schedule_type=schedule_type, name=name)


def _cliff_4() -> VestingScheduleConfig:
    return _schedule(VestingScheduleType.CLIFF_4_YEAR, "4-Year Cliff")


def _open(path: Path):
    return duckdb.connect(str(path), read_only=True)


# ---------------------------------------------------------------------------
# The load-bearing correction: the basis is cumulative, not one year
# ---------------------------------------------------------------------------


def test_forfeiture_basis_is_cumulative_across_the_run(scenario_db: Path):
    """Three years of accrual before termination means three years forfeited."""
    conn = _open(scenario_db)
    try:
        rows = project_forfeitures_for_connection(conn, _cliff_4())
    finally:
        conn.close()

    by_year = {row.simulation_year: row for row in rows}
    termination_year = by_year[2028]

    # Prior-year-only would have found $1,000. The whole in-horizon balance is
    # $3,000, and at tenure 3 a 4-year cliff vests none of it.
    assert termination_year.total_employer_contributions == Decimal("3000.00")
    assert termination_year.forfeited_amount == Decimal("3000.00")
    assert termination_year.vested_amount == Decimal("0.00")


def test_a_fully_vested_termination_forfeits_nothing(scenario_db: Path):
    conn = _open(scenario_db)
    try:
        rows = project_forfeitures_for_connection(
            conn, _schedule(VestingScheduleType.CLIFF_3_YEAR, "3-Year Cliff")
        )
    finally:
        conn.close()

    by_year = {row.simulation_year: row for row in rows}
    assert by_year[2028].total_employer_contributions == Decimal("3000.00")
    assert by_year[2028].forfeited_amount == Decimal("0.00")


# ---------------------------------------------------------------------------
# Gross cost
# ---------------------------------------------------------------------------


def test_gross_cost_is_match_plus_core_per_year(scenario_db: Path):
    conn = _open(scenario_db)
    try:
        gross = query_gross_employer_cost(conn)
    finally:
        conn.close()

    by_year = {row.simulation_year: row for row in gross}
    assert by_year[2025].gross_employer_match == Decimal("2100.00")
    assert by_year[2025].gross_employer_core == Decimal("900.00")
    assert by_year[2025].gross_employer_cost == Decimal("3000.00")
    assert by_year[2025].total_compensation == Decimal("300000.00")
    assert by_year[2025].gross_cost_pct_of_compensation == Decimal("1.00")

    # The termination year keeps the terminated employee's compensation but
    # funds no employer contribution for them.
    assert by_year[2028].gross_employer_cost == Decimal("2000.00")


# ---------------------------------------------------------------------------
# Timing and unmeasurable years
# ---------------------------------------------------------------------------


def _rows(*specs: tuple[int, bool, str]) -> list[ForfeitureYearRow]:
    return [
        ForfeitureYearRow(
            simulation_year=year,
            has_prior_year_basis=has_basis,
            terminated_employee_count=1,
            vesting_eligible_count=1 if has_basis else 0,
            total_employer_contributions=Decimal(amount),
            vested_amount=Decimal("0.00"),
            forfeited_amount=Decimal(amount),
        )
        for year, has_basis, amount in specs
    ]


def test_offsets_apply_the_year_after_the_terminations(scenario_db: Path):
    offsets = build_employer_cost_offsets(
        _rows((2025, False, "0.00"), (2026, True, "500.00"), (2027, True, "800.00")),
        ForfeiturePolicy.OFFSET_EMPLOYER_CONTRIBUTIONS,
    )

    by_year = {row.simulation_year: row for row in offsets}
    assert by_year[2027].source_year == 2026
    assert by_year[2027].offset_amount == Decimal("500.00")


def test_first_year_has_no_offset_rather_than_a_zero_offset():
    offsets = build_employer_cost_offsets(
        _rows((2025, False, "0.00"), (2026, True, "500.00")),
        ForfeiturePolicy.OFFSET_EMPLOYER_CONTRIBUTIONS,
    )

    first = next(row for row in offsets if row.simulation_year == 2025)
    assert first.basis_available is False
    assert first.offset_amount is None
    assert first.source_year is None
    assert "No prior plan year" in (first.unavailable_reason or "")


def test_second_year_is_flagged_because_its_source_has_no_basis():
    """Year one's terminations accrued their money outside the horizon."""
    offsets = build_employer_cost_offsets(
        _rows((2025, False, "0.00"), (2026, True, "500.00")),
        ForfeiturePolicy.OFFSET_EMPLOYER_CONTRIBUTIONS,
    )

    second = next(row for row in offsets if row.simulation_year == 2026)
    assert second.basis_available is False
    assert second.offset_amount is None
    assert second.source_year == 2025


# ---------------------------------------------------------------------------
# Policy semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "policy",
    [
        ForfeiturePolicy.OFFSET_EMPLOYER_CONTRIBUTIONS,
        ForfeiturePolicy.PAY_PLAN_EXPENSES,
    ],
)
def test_cash_policies_reduce_employer_cost(policy: ForfeiturePolicy):
    offsets = build_employer_cost_offsets(
        _rows((2025, False, "0.00"), (2026, True, "500.00"), (2027, True, "800.00")),
        policy,
    )

    applied = next(row for row in offsets if row.simulation_year == 2027)
    assert applied.offset_amount == Decimal("500.00")
    assert applied.participant_allocation == Decimal("0.00")


def test_reallocation_shows_a_zero_offset_with_the_forfeiture_still_disclosed():
    offsets = build_employer_cost_offsets(
        _rows((2025, False, "0.00"), (2026, True, "500.00"), (2027, True, "800.00")),
        ForfeiturePolicy.REALLOCATE_TO_PARTICIPANTS,
    )

    applied = next(row for row in offsets if row.simulation_year == 2027)
    assert applied.basis_available is True
    assert applied.offset_amount == Decimal("0.00")
    # The money is real; it just goes to participants rather than the sponsor.
    assert applied.forfeitures_generated == Decimal("500.00")
    assert applied.participant_allocation == Decimal("500.00")


# ---------------------------------------------------------------------------
# End-to-end series
# ---------------------------------------------------------------------------


def test_series_nets_gross_against_measurable_offsets_only(scenario_db: Path):
    conn = _open(scenario_db)
    try:
        series = compute_employer_cost(
            conn,
            scenario_id="s",
            scenario_name="Scenario",
            schedule=_cliff_4(),
            policy=ForfeiturePolicy.OFFSET_EMPLOYER_CONTRIBUTIONS,
        )
    finally:
        conn.close()

    assert series is not None
    by_year = {row.simulation_year: row for row in series.years}

    # 2028's $3,000 forfeiture is recognized in 2029.
    assert by_year[2029].forfeiture_offset_applied == Decimal("3000.00")
    assert by_year[2029].net_employer_cost == Decimal("-1000.00")

    # 2025 and 2026 have no measurable offset and stay gross-only.
    assert by_year[2025].net_employer_cost is None
    assert by_year[2026].net_employer_cost is None
    assert series.years_without_offset_basis == [2025, 2026]

    assert series.total_forfeiture_offset == Decimal("3000.00")
    assert series.total_net_employer_cost == series.total_gross_employer_cost - Decimal(
        "3000.00"
    )


def test_series_offset_ties_to_the_forfeiture_projection_exactly(scenario_db: Path):
    """The offset is the vesting service's own number, not a re-derivation."""
    conn = _open(scenario_db)
    try:
        forfeitures = project_forfeitures_for_connection(conn, _cliff_4())
        gross = query_gross_employer_cost(conn)
    finally:
        conn.close()

    series = build_employer_cost_series(
        scenario_id="s",
        scenario_name="Scenario",
        schedule_name="4-Year Cliff",
        policy=ForfeiturePolicy.OFFSET_EMPLOYER_CONTRIBUTIONS,
        gross=gross,
        forfeiture_rows=forfeitures,
    )

    measurable = sum(
        (row.forfeited_amount for row in forfeitures if row.has_prior_year_basis),
        Decimal("0.00"),
    )
    assert series.total_forfeiture_offset == measurable


def test_reallocation_leaves_net_equal_to_gross(scenario_db: Path):
    conn = _open(scenario_db)
    try:
        series = compute_employer_cost(
            conn,
            scenario_id="s",
            scenario_name="Scenario",
            schedule=_cliff_4(),
            policy=ForfeiturePolicy.REALLOCATE_TO_PARTICIPANTS,
        )
    finally:
        conn.close()

    assert series is not None
    assert series.total_forfeiture_offset == Decimal("0.00")
    assert series.total_net_employer_cost == series.total_gross_employer_cost


def test_empty_database_yields_no_series(tmp_path: Path):
    path = tmp_path / "empty.duckdb"
    conn = duckdb.connect(str(path))
    conn.execute(SNAPSHOT_DDL)
    conn.close()

    conn = _open(path)
    try:
        assert (
            compute_employer_cost(
                conn,
                scenario_id="s",
                scenario_name="Scenario",
                schedule=_cliff_4(),
                policy=ForfeiturePolicy.OFFSET_EMPLOYER_CONTRIBUTIONS,
            )
            is None
        )
    finally:
        conn.close()
