"""Execute production int_workforce_needs SQL for the first simulation year."""

from datetime import date
from pathlib import Path

import duckdb
import pytest
from jinja2 import Environment

pytestmark = pytest.mark.fast
MODEL = (
    Path(__file__).resolve().parents[1]
    / "dbt/models/intermediate/int_workforce_needs.sql"
)


def render_first_year(year: int) -> str:
    variables = {
        "simulation_year": year,
        "start_year": year,
        "target_growth_rate": 0.02,
        "total_termination_rate": 0.20,
        "new_hire_termination_rate": 0.35,
    }
    env = Environment()
    env.globals.update(
        var=lambda name, default=None: variables.get(name, default),
        config=lambda **kwargs: "",
        ref=lambda name: name,
        is_incremental=lambda: False,
        get_parameter_value=lambda *args: "NULL",
        invocation_id="test",
    )
    return env.from_string(MODEL.read_text()).render()


def needs_for(hire_dates: list[date], year: int = 2026) -> tuple[int, int, int]:
    conn = duckdb.connect()
    conn.execute("""CREATE TABLE int_baseline_workforce (
            employee_id VARCHAR, simulation_year INTEGER, employment_status VARCHAR,
            employee_hire_date DATE, current_compensation DOUBLE, level_id INTEGER)""")
    conn.executemany(
        "INSERT INTO int_baseline_workforce VALUES (?, ?, 'active', ?, 80000, 1)",
        [(f"E{i}", year, hired) for i, hired in enumerate(hire_dates)],
    )
    row = conn.execute(f"""SELECT starting_experienced_count, starting_new_hire_count,
                   expected_experienced_terminations
            FROM ({render_first_year(year)})""").fetchone()
    assert row is not None
    return row


def test_census_prior_year_hires_get_new_hire_turnover() -> None:
    hires = [date(2018, 6, 1)] * 400 + [date(2025, 3, 1)] * 100
    # 0.20 x 400 experienced + 0.35 x 100 prior-year hires
    assert needs_for(hires) == (400, 100, 115)


def test_prior_year_window_is_bounded() -> None:
    hires = [date(2024, 12, 31), date(2025, 1, 1), date(2025, 12, 31), date(2026, 1, 1)]
    experienced, prior_year, _ = needs_for(hires)
    assert (experienced, prior_year) == (2, 2)


def test_census_without_recent_hires_is_unchanged() -> None:
    assert needs_for([date(2015, 1, 1)] * 500) == (500, 0, 100)
