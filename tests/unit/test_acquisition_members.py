"""Execute the acquired-member SQL against small synthetic workforces (#1226)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from jinja2 import Environment

pytestmark = [pytest.mark.fast, pytest.mark.dbt]
DBT = Path(__file__).resolve().parents[2] / "dbt"
YEAR = 2025


def _render(headcount: int) -> str:
    env = Environment()
    joining = [
        {
            "id": "acme",
            "headcount": headcount,
            "effective_date": f"{YEAR}-07-01",
            "ordinal": 1,
        }
    ]
    env.globals.update(
        var=lambda name, default=None: {
            "simulation_year": YEAR,
            "start_year": YEAR,
        }.get(name, default),
        config=lambda **kwargs: "",
        ref=lambda name: name,
        subsystem_seed=lambda name: 42,
        assign_age_band=lambda column: "'age_band'",
        assign_tenure_band=lambda column: "'tenure_band'",
        acquisitions_joining=lambda year: joining,
    )
    model = DBT / "models/intermediate/events/int_acquisition_hire_events.sql"
    return env.from_string(model.read_text()).render()


def _workforce(active: int, inactive: int) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    hash_source = (DBT / "macros/utils/stable_hash.sql").read_text()
    conn.execute(Environment().from_string(hash_source).module.install_stable_hash())
    conn.execute(
        """CREATE TABLE int_baseline_workforce AS
        SELECT 'E' || i AS employee_id, 30 + i % 20 AS current_age,
          i % 7 AS current_tenure, 1 + i % 3 AS level_id,
          50000.0 + i AS current_compensation, ? AS simulation_year,
          CASE WHEN i < ? THEN 'active' ELSE 'terminated' END AS employment_status
        FROM range(?) t(i)""",
        [YEAR, active, active + inactive],
    )
    conn.execute("""CREATE TABLE stg_census_data AS
        SELECT employee_id, NULL::DECIMAL(5,2) AS scheduled_hours_per_week
        FROM int_baseline_workforce""")
    return conn


@pytest.mark.parametrize(("inactive", "headcount"), [(3, 5000), (5000, 3)])
def test_acquisition_with_no_active_staff_fails_loudly(
    inactive: int, headcount: int
) -> None:
    """An acquisition with nobody to sample raises, at either relative size."""
    conn = _workforce(active=0, inactive=inactive)
    with pytest.raises(duckdb.Error, match="no active employees to sample"):
        conn.execute(_render(headcount)).fetchall()


def test_members_are_drawn_only_from_active_staff_with_replacement() -> None:
    conn = _workforce(active=4, inactive=50)
    rows = conn.execute(
        f"SELECT employee_id, compensation_amount, employee_ssn FROM ({_render(25)})"
    ).fetchall()
    assert len(rows) == 25
    assert len({row[0] for row in rows}) == 25
    assert len({row[2] for row in rows}) == 25
    assert all(row[0].startswith("ACQ_acme_") for row in rows)
    assert {row[1] for row in rows} <= {50000.0, 50001.0, 50002.0, 50003.0}
