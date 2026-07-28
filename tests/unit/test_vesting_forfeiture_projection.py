"""Unit tests for multi-year, multi-scenario forfeiture projection (issue #489)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import duckdb
import pytest

from planalign_api.models.vesting import VestingScheduleConfig, VestingScheduleType
from planalign_api.services.vesting_service import VestingService

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
        total_employer_contributions DECIMAL(12, 2)
    )
"""

# Scenario A spans 2025-2027. 'a1' accrues $1,000 by 2025 and terminates in 2026
# at tenure 4; under graded_5_year that is 80% vested, so $200 is forfeited.
SCENARIO_A_ROWS = """
    INSERT INTO fct_workforce_snapshot VALUES
        ('a1', 2025, 'ACTIVE',     DATE '2022-01-01', NULL,              3, '2-4', 2080, 1000.00),
        ('a2', 2025, 'TERMINATED', DATE '2024-01-01', DATE '2025-06-30', 1, '<2',  1040,    0.00),
        ('a1', 2026, 'TERMINATED', DATE '2022-01-01', DATE '2026-06-30', 4, '2-4', 1040,    0.00),
        ('a3', 2026, 'ACTIVE',     DATE '2023-01-01', NULL,              3, '2-4', 2080,  500.00),
        ('a3', 2027, 'ACTIVE',     DATE '2023-01-01', NULL,              4, '2-4', 2080,  750.00)
"""

# Scenario B spans only 2026-2027, so the union of years is 2025-2027 with a gap.
SCENARIO_B_ROWS = """
    INSERT INTO fct_workforce_snapshot VALUES
        ('b1', 2026, 'ACTIVE',     DATE '2025-01-01', NULL,              1, '<2',  2080,  500.00),
        ('b1', 2027, 'TERMINATED', DATE '2025-01-01', DATE '2027-06-30', 2, '2-4', 2080,    0.00)
"""


@dataclass
class _Resolved:
    path: Path
    exists: bool


class _StubResolver:
    """Maps scenario ids to database paths; unknown ids resolve as missing."""

    def __init__(self, paths: dict[str, Path]):
        self._paths = paths

    def resolve(self, workspace_id: str, scenario_id: str) -> _Resolved:
        path = self._paths.get(scenario_id, Path("/nonexistent.duckdb"))
        return _Resolved(path=path, exists=path.exists())


def _write_scenario(path: Path, rows: str) -> Path:
    conn = duckdb.connect(str(path))
    try:
        conn.execute(SNAPSHOT_DDL)
        conn.execute(rows)
    finally:
        conn.close()
    return path


def _service(paths: dict[str, Path]) -> VestingService:
    service = VestingService(storage=Mock())
    service.db_resolver = _StubResolver(paths)
    return service


def _graded_5() -> VestingScheduleConfig:
    return VestingScheduleConfig(
        schedule_type=VestingScheduleType.GRADED_5_YEAR, name="5-Year Graded"
    )


@pytest.fixture
def scenario_a(tmp_path: Path) -> Path:
    return _write_scenario(tmp_path / "a.duckdb", SCENARIO_A_ROWS)


@pytest.fixture
def scenario_b(tmp_path: Path) -> Path:
    return _write_scenario(tmp_path / "b.duckdb", SCENARIO_B_ROWS)


def test_first_year_is_flagged_rather_than_reported_as_zero(scenario_a: Path):
    """Year one has no prior-year contribution basis, so it is not a measured $0."""
    service = _service({"a": scenario_a})

    result = service.project_forfeitures("ws", [("a", "Scenario A")], _graded_5())

    first = result.scenarios[0].years[0]
    assert first.simulation_year == 2025
    assert first.has_prior_year_basis is False
    assert first.vesting_eligible_count == 0
    assert first.forfeited_amount == Decimal("0")
    # The year is still real: its terminations are reported, just not vestable.
    assert first.terminated_employee_count == 1


def test_later_years_carry_a_prior_year_basis(scenario_a: Path):
    service = _service({"a": scenario_a})

    result = service.project_forfeitures("ws", [("a", "Scenario A")], _graded_5())

    assert [row.has_prior_year_basis for row in result.scenarios[0].years] == [
        False,
        True,
        True,
    ]


def test_forfeiture_amount_matches_schedule(scenario_a: Path):
    """'a1' terminates at tenure 4 on a $1,000 basis: 80% vested, $200 forfeited."""
    service = _service({"a": scenario_a})

    result = service.project_forfeitures("ws", [("a", "Scenario A")], _graded_5())

    year_2026 = result.scenarios[0].years[1]
    assert year_2026.simulation_year == 2026
    assert year_2026.vesting_eligible_count == 1
    assert year_2026.total_employer_contributions == Decimal("1000.00")
    assert year_2026.vested_amount == Decimal("800.00")
    assert year_2026.forfeited_amount == Decimal("200.00")


def test_scenario_totals_sum_the_year_rows(scenario_a: Path):
    service = _service({"a": scenario_a})

    series = service.project_forfeitures(
        "ws", [("a", "Scenario A")], _graded_5()
    ).scenarios[0]

    assert series.total_forfeited == sum(row.forfeited_amount for row in series.years)
    assert series.total_vested == sum(row.vested_amount for row in series.years)
    assert series.total_forfeited == Decimal("200.00")


def test_union_of_years_across_scenarios_with_different_ranges(
    scenario_a: Path, scenario_b: Path
):
    """Scenario B starts a year later; the union spans both, per scenario gaps."""
    service = _service({"a": scenario_a, "b": scenario_b})

    result = service.project_forfeitures(
        "ws", [("a", "Scenario A"), ("b", "Scenario B")], _graded_5()
    )

    assert result.years == [2025, 2026, 2027]
    by_id = {item.scenario_id: item for item in result.scenarios}
    assert [row.simulation_year for row in by_id["a"].years] == [2025, 2026, 2027]
    # B has no 2025 row at all — the UI renders a gap rather than a zero.
    assert [row.simulation_year for row in by_id["b"].years] == [2026, 2027]


def test_each_scenario_first_year_is_its_own(scenario_a: Path, scenario_b: Path):
    """B's first year is 2026, so 2026 is unflagged for A but flagged for B."""
    service = _service({"a": scenario_a, "b": scenario_b})

    result = service.project_forfeitures(
        "ws", [("a", "Scenario A"), ("b", "Scenario B")], _graded_5()
    )

    by_id = {item.scenario_id: item for item in result.scenarios}
    a_2026 = next(r for r in by_id["a"].years if r.simulation_year == 2026)
    b_2026 = next(r for r in by_id["b"].years if r.simulation_year == 2026)
    assert a_2026.has_prior_year_basis is True
    assert b_2026.has_prior_year_basis is False


def test_missing_database_is_skipped_not_fatal(scenario_a: Path):
    """One unbuilt scenario must not fail the whole request."""
    service = _service({"a": scenario_a})

    result = service.project_forfeitures(
        "ws", [("a", "Scenario A"), ("ghost", "Never Run")], _graded_5()
    )

    assert [item.scenario_id for item in result.scenarios] == ["a"]
    assert [item.scenario_id for item in result.skipped] == ["ghost"]
    assert result.skipped[0].reason


def test_empty_database_is_skipped(tmp_path: Path):
    """A database with the table but no rows yields no years, so it is skipped."""
    empty = tmp_path / "empty.duckdb"
    conn = duckdb.connect(str(empty))
    try:
        conn.execute(SNAPSHOT_DDL)
    finally:
        conn.close()
    service = _service({"empty": empty})

    result = service.project_forfeitures("ws", [("empty", "Empty")], _graded_5())

    assert result.scenarios == []
    assert [item.scenario_id for item in result.skipped] == ["empty"]


def test_grouped_query_agrees_with_the_single_year_query(scenario_a: Path):
    """The multi-year path must not diverge from the validated per-year path."""
    service = _service({"a": scenario_a})
    conn = duckdb.connect(str(scenario_a), read_only=True)
    try:
        per_year = service._get_terminated_employees(conn, 2026)
        grouped = [
            row
            for row in service._get_terminated_employees_all_years(conn)
            if row["simulation_year"] == 2026
        ]
    finally:
        conn.close()

    assert [row["employee_id"] for row in per_year] == [
        row["employee_id"] for row in grouped
    ]
    assert [row["total_employer_contributions"] for row in per_year] == [
        row["total_employer_contributions"] for row in grouped
    ]


def test_hours_credit_reduces_vesting(scenario_a: Path):
    """Failing the hours threshold drops effective tenure by a year (4 -> 3)."""
    service = _service({"a": scenario_a})
    schedule = VestingScheduleConfig(
        schedule_type=VestingScheduleType.GRADED_5_YEAR,
        name="5-Year Graded",
        require_hours_credit=True,
        hours_threshold=2080,  # above 'a1' 2026's 1,040 hours, so credit is denied
    )

    result = service.project_forfeitures("ws", [("a", "Scenario A")], schedule)

    year_2026 = result.scenarios[0].years[1]
    # tenure 4 -> 3 under the penalty: 60% vested, so $400 forfeited instead of $200.
    assert year_2026.vested_amount == Decimal("600.00")
    assert year_2026.forfeited_amount == Decimal("400.00")
