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
    source = Path("dbt/models/staging/stg_census_data.sql").read_text()
    source = source.split("{% set census_pay_basis", 1)[1].split(
        "-- Calculate eligibility", 1
    )[0]
    exported = {} if basis is None else {"census_pay_basis": basis}
    sql = (
        Environment()
        .from_string("{% set census_pay_basis" + source)
        .render(var=lambda key, default=None: exported.get(key, default))
    )
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
    source = Path("dbt/models/staging/stg_census_data.sql").read_text()
    source = source.split("{% set census_pay_basis", 1)[1].split(
        "-- Calculate eligibility", 1
    )[0]
    sql = (
        Environment()
        .from_string("{% set census_pay_basis" + source)
        .render(
            var=lambda key, default=None: {
                "census_pay_basis": "earnings",
                "census_pay_min_days": 200,
            }.get(key, default)
        )
    )
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
    source = Path("dbt/models/staging/stg_census_data.sql").read_text()
    source = source.split("{% set census_pay_basis", 1)[1].split(
        "-- Calculate eligibility", 1
    )[0]
    sql = (
        Environment()
        .from_string("{% set census_pay_basis" + source)
        .render(
            var=lambda key, default=None: {"census_pay_basis": "earnings"}.get(
                key, default
            )
        )
    )
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
