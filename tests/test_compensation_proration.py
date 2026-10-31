"""Execute production compensation CTEs in DuckDB against calendar-day oracles."""

from datetime import date
from pathlib import Path

import duckdb
import pytest
from jinja2 import Environment, StrictUndefined

pytestmark = pytest.mark.fast
DBT = Path(__file__).resolve().parents[1] / "dbt"


def render_ctes(path: str, start: str, end: str, year: int) -> str:
    source = (DBT / path).read_text().split(start, 1)[1].split(end, 1)[0]
    return (
        Environment(undefined=StrictUndefined)
        .from_string(start + source)
        .render(
            simulation_year=year,
            var=lambda name, default=None: {
                "plan_year_start_date": f"{year}-01-01",
                "plan_year_end_date": f"{year}-12-31",
            }.get(name, default),
            evt_hire=lambda: "'hire'",
            evt_promotion=lambda: "'promotion'",
            evt_raise=lambda: "'raise'",
            evt_termination=lambda: "'termination'",
            status_terminated=lambda: "'terminated'",
            status_active=lambda: "'active'",
            is_compensation_event=lambda column: (
                f"{column} IN ('hire', 'promotion', 'raise')"
            ),
        )
    )


def setup_workforce(conn: duckdb.DuckDBPyConnection, year: int) -> None:
    conn.execute("""CREATE TABLE deduplicated_workforce (
        employee_id VARCHAR, employee_hire_date DATE, termination_date DATE,
        employment_status VARCHAR, employee_gross_compensation DOUBLE)""")
    conn.executemany(
        "INSERT INTO deduplicated_workforce VALUES (?, ?::DATE, ?::DATE, ?, ?)",
        [
            ("full", "2020-01-01", None, "active", 100000),
            ("jan_hire", f"{year}-01-01", None, "active", 100000),
            ("hire", f"{year}-07-01", None, "active", 100000),
            ("hire_fallback", f"{year}-07-01", None, "active", 100000),
            ("term", "2020-01-01", f"{year}-06-30", "terminated", 100000),
            ("hire_term", f"{year}-03-01", f"{year}-09-30", "terminated", 100000),
            ("raise", "2020-01-01", None, "active", 120000),
            ("same_rate", "2020-01-01", None, "active", 100000),
        ],
    )
    conn.execute("""CREATE TABLE current_year_events (
        employee_id VARCHAR, event_type VARCHAR, effective_date DATE,
        compensation_amount DOUBLE, previous_compensation DOUBLE)""")
    conn.executemany(
        "INSERT INTO current_year_events VALUES (?, ?, ?::DATE, ?, ?)",
        [
            ("jan_hire", "hire", f"{year}-01-01", 100000, None),
            ("hire", "hire", f"{year}-07-01", 100000, None),
            ("term", "termination", f"{year}-06-30", None, 100000),
            ("hire_term", "hire", f"{year}-03-01", 100000, None),
            ("hire_term", "termination", f"{year}-09-30", None, 100000),
            ("raise", "raise", f"{year}-07-01", 120000, 100000),
            ("same_rate", "raise", f"{year}-07-01", 100000, 100000),
        ],
    )


@pytest.mark.parametrize("year", [2027, 2028, 2029])
def test_workforce_earned_compensation(year: int) -> None:
    ctes = render_ctes(
        "models/intermediate/int_workforce_state_accumulator.sql",
        "compensation_events AS (",
        "\nSELECT\n  '{{ scenario_id }}'",
        year,
    )
    days = (date(year + 1, 1, 1) - date(year, 1, 1)).days
    first = (date(year, 7, 1) - date(year, 1, 1)).days
    hired = (date(year, 10, 1) - date(year, 3, 1)).days
    with duckdb.connect(":memory:") as conn:
        setup_workforce(conn, year)
        actual = dict(
            conn.execute(
                "WITH " + ctes + " SELECT * FROM prorated_compensation"
            ).fetchall()
        )
    assert actual["full"] == actual["jan_hire"] == 100000
    assert actual["same_rate"] == pytest.approx(100000, abs=1e-10)
    assert actual["hire"] == pytest.approx(100000 * (days - first) / days)
    assert actual["hire_fallback"] == actual["hire"]
    assert actual["term"] == pytest.approx(100000 * first / days)
    assert actual["hire_term"] == pytest.approx(100000 * hired / days)
    assert actual["raise"] == pytest.approx(
        (100000 * first + 120000 * (days - first)) / days
    )
    assert actual["term"] + actual["hire"] == pytest.approx(100000, abs=1e-10)


@pytest.mark.parametrize("year", [2027, 2028, 2029])
def test_census_plan_year_compensation(year: int) -> None:
    ctes = (
        render_ctes(
            "models/staging/stg_census_data.sql",
            "annualized_data AS (",
            "-- Calculate eligibility and enrollment fields",
            year,
        )
        .rstrip()
        .removesuffix(",")
    )
    with duckdb.connect(":memory:") as conn:
        setup_workforce(conn, year)
        conn.execute("""CREATE TABLE raw_data AS SELECT *,
            termination_date AS employee_termination_date, 1 AS rn
            FROM deduplicated_workforce""")
        conn.execute(
            "INSERT INTO raw_data VALUES "
            "('outside', ?, NULL, 'active', 100000, NULL, 1)",
            [date(year + 1, 1, 1)],
        )
        actual = dict(
            conn.execute(
                "WITH "
                + ctes
                + " SELECT employee_id, computed_plan_year_compensation FROM comp_data"
            ).fetchall()
        )
    days = (date(year + 1, 1, 1) - date(year, 1, 1)).days
    first = (date(year, 7, 1) - date(year, 1, 1)).days
    assert actual["full"] == actual["jan_hire"] == 100000
    assert actual["hire"] == pytest.approx(100000 * (days - first) / days)
    assert actual["term"] == pytest.approx(100000 * first / days)
    assert actual["hire_term"] == pytest.approx(
        100000 * (date(year, 10, 1) - date(year, 3, 1)).days / days
    )
    assert actual["outside"] == 0


@pytest.mark.parametrize("year", [2027, 2028, 2029])
def test_proration_diagnostic_recovers_calendar_days(year: int) -> None:
    source = (
        DBT / "models/marts/data_quality/dq_e057_new_hire_termination_validation.sql"
    ).read_text()
    query = source.split("FROM (\n        SELECT\n            wb.*,", 1)[1]
    query = "SELECT wb.*," + query.split("FROM validation_base wb", 1)[0]
    query += " FROM validation_base wb"
    days = (date(year + 1, 1, 1) - date(year, 1, 1)).days
    employed = (date(year + 1, 1, 1) - date(year, 7, 1)).days
    with duckdb.connect(":memory:") as conn:
        conn.execute(
            """CREATE TABLE validation_base AS SELECT
            ?::INTEGER simulation_year, 'active' employment_status,
            NULL::DATE termination_date, ?::DATE employee_hire_date,
            100000.0 current_compensation, ?::DOUBLE prorated_annual_compensation""",
            [year, date(year, 7, 1), 100000 * employed / days],
        )
        conn.execute("CREATE TABLE diagnostic AS " + query)
        assert conn.execute(
            "SELECT expected_days, actual_days FROM diagnostic"
        ).fetchone() == (employed, employed)
        conn.execute(
            "UPDATE validation_base SET employee_hire_date = DATE '2020-01-01', "
            "prorated_annual_compensation = current_compensation"
        )
        assert conn.execute(
            "SELECT expected_days, actual_days FROM (" + query + ")"
        ).fetchone() == (days, days)
