"""Writing the year-end workforce back out as a census (#1078)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from planalign_orchestrator import census_rollforward
from planalign_orchestrator.census_year import infer_census_year

pytestmark = [pytest.mark.fast]


def _original_census(tmp_path: Path) -> Path:
    path = tmp_path / "census.parquet"
    with duckdb.connect() as conn:
        conn.execute(f"""
            COPY (
              SELECT * FROM (VALUES
                ('E1', DATE '2019-04-01', 30.0, 'Ops'),
                ('E2', DATE '2024-08-01', NULL, 'Sales'),
                ('E3', DATE '2015-01-01', 40.0, 'Ops')
              ) t(employee_id, employee_hire_date, scheduled_hours_per_week, department)
            ) TO '{path}' (FORMAT parquet)
            """)
    return path


def _bridge_db(tmp_path: Path) -> Path:
    """A finished 2025 simulation: E3 left, N1 was hired, N2 hired and left."""
    path = tmp_path / "bridge.duckdb"
    with duckdb.connect(str(path)) as conn:
        conn.execute("""
            CREATE TABLE fct_workforce_snapshot AS SELECT * FROM (VALUES
              ('E1', 'S1', DATE '1980-01-01', DATE '2019-04-01', 2025, 'active',
                61800.0, 61000.0, TRUE, 0.06, DATE '2019-07-01'),
              ('E2', 'S2', DATE '1990-01-01', DATE '2024-08-01', 2025, 'active',
                52000.0, 51500.0, TRUE, 0.0, DATE '2024-11-01'),
              ('E3', 'S3', DATE '1970-01-01', DATE '2015-01-01', 2025, 'terminated',
                90000.0, 40000.0, FALSE, 0.0, DATE '2015-04-01'),
              ('N1', 'S4', DATE '1995-01-01', DATE '2025-07-01', 2025, 'active',
                48000.0, 24000.0, FALSE, 0.03, NULL),
              ('E1', 'S1', DATE '1980-01-01', DATE '2019-04-01', 2024, 'active',
                60000.0, 60000.0, TRUE, 0.06, DATE '2019-07-01')
            ) t(employee_id, employee_ssn, employee_birth_date, employee_hire_date,
                simulation_year, employment_status, current_compensation,
                prorated_annual_compensation, is_enrolled_flag,
                current_deferral_rate, employee_eligibility_date)
            """)
        conn.execute("""
            CREATE TABLE fct_yearly_events AS SELECT * FROM (VALUES
              (2025, 'hire'), (2025, 'hire'), (2025, 'termination'),
              (2025, 'termination'), (2025, 'raise'), (2024, 'hire')
            ) t(simulation_year, event_type)
            """)
    return path


def _write(tmp_path: Path, pay_basis: str) -> dict[str, tuple]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    out = tmp_path / f"bridge_{pay_basis}.parquet"
    with duckdb.connect(str(_bridge_db(tmp_path)), read_only=True) as conn:
        census_rollforward._write_census(
            conn, _original_census(tmp_path), 2025, pay_basis, out
        )
        rows = conn.execute(f"""
            SELECT employee_id, CAST(employee_gross_compensation AS DOUBLE),
              CAST(employee_deferral_rate AS DOUBLE),
              CAST(scheduled_hours_per_week AS DOUBLE), department, simulated_employee, active,
              employee_termination_date
            FROM read_parquet('{out}')
            """).fetchall()
    return {row[0]: row[1:] for row in rows}


def test_writes_only_the_year_end_active_workforce(tmp_path: Path) -> None:
    assert set(_write(tmp_path, "earnings")) == {"E1", "E2", "N1"}


def test_pay_is_the_year_end_rate(tmp_path: Path) -> None:
    rows = _write(tmp_path, "earnings")
    assert rows["E1"][0] == 61800.0
    assert _write(tmp_path / "rate", "annual_rate")["N1"][0] == 48000.0


def test_bridge_year_hires_keep_earnings_for_staging_to_annualize(
    tmp_path: Path,
) -> None:
    assert _write(tmp_path, "earnings")["N1"][0] == 24000.0


def test_only_enrolled_employees_keep_a_deferral_rate(tmp_path: Path) -> None:
    rows = _write(tmp_path, "earnings")
    assert rows["E1"][1] == pytest.approx(0.06)
    assert rows["N1"][1] == 0


def test_census_only_columns_carry_over_and_hires_are_flagged(
    tmp_path: Path,
) -> None:
    rows = _write(tmp_path, "earnings")
    assert rows["E1"][2:7] == (30.0, "Ops", False, True, None)
    assert rows["N1"][2:5] == (None, None, True)


def test_bridge_census_reads_as_the_bridge_year(tmp_path: Path) -> None:
    _write(tmp_path, "earnings")
    assert infer_census_year(tmp_path / "bridge_earnings.parquet") == 2025


def test_counts_only_the_bridge_years_events(tmp_path: Path) -> None:
    with duckdb.connect(str(_bridge_db(tmp_path)), read_only=True) as conn:
        assert census_rollforward._event_counts(conn, 2025, 2025) == (2, 2)


def test_refuses_a_census_that_is_already_current(tmp_path: Path) -> None:
    census = _original_census(tmp_path)
    with pytest.raises(ValueError, match="already from 2024"):
        census_rollforward.roll_forward_census(
            None,  # type: ignore[arg-type]
            census,
            2024,
            tmp_path / "out.parquet",
            tmp_path / "db.duckdb",
        )


def test_simulated_hires_get_no_ssn_so_staging_assigns_a_safe_one(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "earnings")
    rows = dict(
        duckdb.connect()
        .execute(
            "SELECT employee_id, employee_ssn FROM read_parquet(?)",
            [str(tmp_path / "bridge_earnings.parquet")],
        )
        .fetchall()
    )
    assert rows == {"E1": "S1", "E2": "S2", "N1": None}
