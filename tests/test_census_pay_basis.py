"""Bounded earnings-rule coverage using the production staging CTEs."""

from pathlib import Path

import duckdb
import pytest
from jinja2 import Environment

from planalign_orchestrator.config import load_simulation_config, to_dbt_vars
from planalign_orchestrator.config.loader import SimulationConfig
from planalign_orchestrator.config.dbt_var_validation import validate_dbt_vars

pytestmark = pytest.mark.fast


@pytest.mark.parametrize("basis", ["annual_rate", "earnings"])
def test_config(basis: str) -> None:
    cfg = load_simulation_config("config/simulation_config.yaml").model_dump()
    cfg["setup"]["census_pay_basis"] = basis
    exported = to_dbt_vars(SimulationConfig.model_validate(cfg))
    if basis == "earnings":
        assert "census_pay_basis" not in exported
    else:
        assert exported["census_pay_basis"] == basis
    cfg["setup"]["census_pay_basis"] = "invalid"
    exported = to_dbt_vars(SimulationConfig.model_validate(cfg))
    assert exported["census_pay_basis"] == "invalid"
    assert validate_dbt_vars(exported)
    cfg["setup"].pop("census_pay_basis")
    assert "census_pay_basis" not in to_dbt_vars(SimulationConfig.model_validate(cfg))


def staging_ctes(dbt_vars: dict[str, object]) -> str:
    """The production staging CTEs from the census calendar to comp_data."""
    macro = Path("dbt/macros/utils/census_plan_calendar.sql").read_text()
    source = Path("dbt/models/staging/stg_census_data.sql").read_text()
    body = source.split("-- Census year and census plan year", 1)[1]
    body = body.split("\n", 1)[1].split("-- Calculate eligibility", 1)[0]
    return (
        Environment()
        .from_string(macro + body)
        .render(var=lambda key, default=None: dbt_vars.get(key, default))
    )


def seed(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""CREATE TABLE raw_data AS SELECT *, 1 AS rn FROM (VALUES
      ('july', DATE '2028-07-01', NULL::DATE, 18400., TRUE),
      ('dec', DATE '2028-12-20', NULL::DATE, 1000., TRUE),
      ('zero', DATE '2028-08-01', NULL::DATE, 0., TRUE),
      ('full', DATE '2020-01-01', NULL::DATE, 50000., TRUE),
      ('leaver', DATE '2028-07-01', DATE '2028-09-30', 10000., FALSE)
    ) t(employee_id, employee_hire_date, employee_termination_date,
        employee_gross_compensation, active)""")


@pytest.mark.parametrize("basis", [None, "annual_rate", "earnings"])
def test_staging(basis: str | None) -> None:
    exported = {} if basis is None else {"census_pay_basis": basis}
    sql = staging_ctes(exported)
    with duckdb.connect(":memory:") as conn:
        seed(conn)
        rows = conn.execute(
            "WITH "
            + sql.rstrip().removesuffix(",")
            + " SELECT employee_id, employee_annualized_compensation, "
            "computed_plan_year_compensation FROM comp_data"
        ).fetchall()
        actual = {row[0]: row[1:] for row in rows}
    expected = 18400 if basis == "annual_rate" else 36600
    assert actual["july"][0] == pytest.approx(expected)
    assert actual["full"][0] == 50000
    assert actual["leaver"][0] == 10000
    if basis != "annual_rate":
        assert actual["dec"] == (36600, 1000)
        assert actual["zero"] == (36600, 0)
        assert actual["july"][1] == 18400
    else:
        assert actual["dec"][0] == 1000
        assert actual["zero"][0] == 0


def test_staging_no_qualifying_hires() -> None:
    sql = staging_ctes({"census_pay_basis": "earnings", "census_pay_min_days": 200})
    with duckdb.connect(":memory:") as conn:
        seed(conn)
        rows = conn.execute(
            "WITH "
            + sql.rstrip().removesuffix(",")
            + " SELECT employee_annualized_compensation = employee_gross_compensation "
            "FROM comp_data"
        ).fetchall()
    assert all(row[0] for row in rows)


def test_future_outliers_and_text_active() -> None:
    sql = staging_ctes({"census_pay_basis": "earnings"})
    with duckdb.connect(":memory:") as conn:
        conn.execute("""CREATE TABLE raw_data AS
          SELECT 'prior_' || i AS employee_id, DATE '2020-01-01' AS employee_hire_date,
            NULL::DATE AS employee_termination_date, 50000. AS employee_gross_compensation,
            'Active' AS active, 1 AS rn FROM range(300) t(i)""")
        conn.execute("""INSERT INTO raw_data VALUES
          ('july', DATE '2025-07-01', NULL, 18400., 'Active', 1),
          ('future1', DATE '2026-01-01', NULL, 1000., 'Active', 1),
          ('future2', DATE '2026-01-02', NULL, 1000., 'Active', 1)""")
        # Ensure the latest meaningful hire year reaches the 1% threshold.
        conn.execute("""INSERT INTO raw_data
          SELECT 'current_' || i, DATE '2025-01-01', NULL, 50000., 'Active', 1
          FROM range(4) t(i)""")
        row = conn.execute(
            "WITH "
            + sql.rstrip().removesuffix(",")
            + " SELECT employee_annualized_compensation FROM comp_data WHERE employee_id = 'july'"
        ).fetchone()
    assert row is not None
    assert row[0] == pytest.approx(36500)


def plan_year(dbt_vars: dict[str, object]) -> tuple:
    with duckdb.connect(":memory:") as conn:
        seed(conn)
        row = conn.execute(
            "WITH "
            + staging_ctes(dbt_vars).rstrip().removesuffix(",")
            + " SELECT plan_start, plan_end FROM plan_calendar"
        ).fetchone()
    assert row is not None
    return tuple(str(d) for d in row)


def test_plan_year_defaults_to_the_census_year() -> None:
    assert plan_year({}) == ("2028-01-01", "2028-12-31")


def test_explicit_plan_year_dates_win() -> None:
    dates = {"plan_year_start_date": "2024-01-01", "plan_year_end_date": "2024-12-31"}
    assert plan_year(dates) == ("2024-01-01", "2024-12-31")


@pytest.mark.parametrize(
    "dates",
    [{"plan_year_start_date": "2025-07-01"}, {"plan_year_end_date": "2026-06-30"}],
)
def test_one_plan_year_date_implies_the_other(dates: dict[str, object]) -> None:
    assert plan_year(dates) == ("2025-07-01", "2026-06-30")


def test_annual_rate_prorates_within_the_census_plan_year() -> None:
    with duckdb.connect(":memory:") as conn:
        seed(conn)
        rows = dict(
            conn.execute(
                "WITH "
                + staging_ctes({"census_pay_basis": "annual_rate"})
                .rstrip()
                .removesuffix(",")
                + " SELECT employee_id, days_active_in_year FROM annualized_data"
            ).fetchall()
        )
    assert rows["july"] == 184
    assert rows["full"] == 366
