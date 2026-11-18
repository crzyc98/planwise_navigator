"""Census hourly rate from hourly_rate, hours_worked or scheduled hours (#1230)."""

from __future__ import annotations

import duckdb
import pytest

from planalign_api.services.file_service import FileService
from planalign_orchestrator.census_hourly_rate import (
    hourly_rate_bounds,
    summarize_hourly_rates,
)
from tests.test_census_pay_basis import staging_ctes

pytestmark = pytest.mark.fast

LOW, HIGH = hourly_rate_bounds()

# Synthetic census year 2028 (a leap year: 366 days). Columns: id, hire date,
# gross pay, hourly_rate, hours_worked, scheduled_hours_per_week.
ROWS = """
  ('given',  DATE '2020-01-01', 41600., 22.5, NULL, NULL),
  ('worked', DATE '2020-01-01', 30000., NULL, 1500., NULL),
  ('weekly', DATE '2020-01-01', 41600., NULL, NULL, 40.),
  ('midyear_worked', DATE '2028-07-01', 18400., NULL, 920., NULL),
  ('midyear_weekly', DATE '2028-07-01', 18400., NULL, NULL, 40.),
  ('all_three', DATE '2020-01-01', 40000., 25., 1000., 30.),
  ('hours_and_weekly', DATE '2020-01-01', 40000., NULL, 2000., 20.),
  ('blank', DATE '2020-01-01', 2000., NULL, NULL, NULL),
  ('too_low', DATE '2020-01-01', 41600., 5., NULL, NULL),
  ('too_high', DATE '2020-01-01', 50000., NULL, 10., NULL),
  ('zero_hours', DATE '2020-01-01', 50000., NULL, 0., NULL),
  ('at_minimum', DATE '2020-01-01', 15080., 7.25, NULL, NULL)
"""


def _staged(basis: str) -> dict[str, tuple]:
    dbt_vars = {
        "census_pay_basis": basis,
        "census_hourly_rate_min": LOW,
        "census_hourly_rate_max": HIGH,
    }
    with duckdb.connect(":memory:") as conn:
        conn.execute(f"""CREATE TABLE raw_data AS
          SELECT employee_id, employee_hire_date, NULL::DATE AS employee_termination_date,
            employee_gross_compensation, TRUE AS active, hourly_rate, hours_worked,
            CAST(scheduled_hours_per_week AS DECIMAL(5,2)) AS scheduled_hours_per_week,
            1 AS rn
          FROM (VALUES {ROWS}) t(employee_id, employee_hire_date,
            employee_gross_compensation, hourly_rate, hours_worked,
            scheduled_hours_per_week)""")
        rows = conn.execute(
            "WITH "
            + staging_ctes(dbt_vars).rstrip().removesuffix(",")
            + " SELECT employee_id, census_hourly_rate, census_hourly_rate_source"
            " FROM hourly_rates"
        ).fetchall()
    return {row[0]: row[1:] for row in rows}


def test_bounds_come_from_the_dbt_project() -> None:
    assert (LOW, HIGH) == (7.25, 500.0)


def test_each_column_alone_gives_the_hand_checked_rate() -> None:
    rows = _staged("earnings")
    assert rows["given"] == (22.5, "hourly_rate")
    # 30,000 / 1,500 hours
    assert rows["worked"] == (pytest.approx(20.0), "hours_worked")
    # 41,600 / (40 x 52)
    assert rows["weekly"] == (pytest.approx(20.0), "scheduled_hours_per_week")


def test_mid_year_hire_under_earnings() -> None:
    rows = _staged("earnings")
    # Half-year earnings over half-year hours: 18,400 / 920.
    assert rows["midyear_worked"] == (pytest.approx(20.0), "hours_worked")
    # Weekly hours use the annualized rate: 18,400 x 366 / 184 days = 36,600,
    # over 40 x 52 hours.
    assert rows["midyear_weekly"][0] == pytest.approx(36600 / 2080)


def test_mid_year_hire_under_annual_rate_uses_census_year_pay() -> None:
    rows = _staged("annual_rate")
    # 18,400 annual rate x 184 / 366 days = 9,250.27 paid, over 920 hours.
    assert rows["midyear_worked"][0] == pytest.approx(18400 * 184 / 366 / 920)
    assert rows["midyear_weekly"][0] == pytest.approx(18400 / 2080)


def test_precedence_is_hourly_rate_then_hours_worked_then_weekly_hours() -> None:
    rows = _staged("earnings")
    assert rows["all_three"] == (25.0, "hourly_rate")
    assert rows["hours_and_weekly"] == (pytest.approx(20.0), "hours_worked")


def test_blank_row_is_not_hourly() -> None:
    assert _staged("earnings")["blank"] == (None, None)


def test_out_of_bounds_rates_are_flagged_and_dropped() -> None:
    rows = _staged("earnings")
    assert rows["too_low"] == (None, "out_of_bounds")
    assert rows["too_high"] == (None, "out_of_bounds")
    assert rows["zero_hours"] == (None, "out_of_bounds")
    assert rows["at_minimum"] == (7.25, "hourly_rate")


def _summary_table(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(f"""CREATE TABLE census AS SELECT * FROM (VALUES {ROWS})
      t(employee_id, employee_hire_date, employee_gross_compensation, hourly_rate,
        hours_worked, scheduled_hours_per_week)""")


def test_import_summary_counts_rates_blanks_and_bad_rates() -> None:
    with duckdb.connect(":memory:") as conn:
        _summary_table(conn)
        columns = [r[0] for r in conn.execute("DESCRIBE census").fetchall()]
        summary = summarize_hourly_rates(conn, "census", columns)
    assert summary is not None
    assert summary.columns_present == (
        "hourly_rate",
        "hours_worked",
        "scheduled_hours_per_week",
    )
    assert (summary.with_rate, summary.blank, summary.out_of_bounds) == (8, 1, 3)
    assert summary.multiple_columns == 2
    assert summary.by_source == {
        "hourly_rate": 3,
        "hours_worked": 3,
        "scheduled_hours_per_week": 2,
    }


def test_import_summary_is_absent_without_hourly_columns() -> None:
    with duckdb.connect(":memory:") as conn:
        conn.execute("CREATE TABLE census AS SELECT 'E1' AS employee_id")
        assert summarize_hourly_rates(conn, "census", ["employee_id"]) is None


def test_census_upload_reports_hourly_rates(tmp_path) -> None:
    csv = (
        "employee_id,employee_gross_compensation,hourly_wage,hours_worked\n"
        "E1,41600,22.50,\n"
        "E2,30000,,1500\n"
        "E3,2000,,\n"
        "E4,50000,$3.00,2000\n"
    )
    service = FileService(tmp_path)
    _, metadata, _ = service.save_uploaded_file("ws", csv.encode(), "census.csv")
    summary = metadata["hourly_rate_summary"]
    assert {"original": "hourly_wage", "canonical": "hourly_rate"} in metadata[
        "column_renames"
    ]
    assert (summary["with_rate"], summary["blank"], summary["out_of_bounds"]) == (
        2,
        1,
        1,
    )
    assert summary["multiple_columns"] == 1


def test_census_upload_without_hourly_columns_has_no_summary(tmp_path) -> None:
    csv = "employee_id,employee_gross_compensation\nE1,41600\n"
    _, metadata, _ = FileService(tmp_path).save_uploaded_file(
        "ws", csv.encode(), "census.csv"
    )
    assert metadata["hourly_rate_summary"] is None
