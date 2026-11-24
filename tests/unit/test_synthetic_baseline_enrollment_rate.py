"""Census deferral rates reach escalation and match response unchanged (#1262).

int_synthetic_baseline_enrollment_events used to cap census rates at the plan
deferral cap (75%) while the state accumulator kept the census rate, so with an
escalation cap above 75% a 95% saver was "escalated" down to 76%.
"""

from pathlib import Path
from typing import Any

import duckdb
import pytest
from jinja2 import Environment, StrictUndefined

pytestmark = pytest.mark.fast
DBT = Path(__file__).resolve().parents[2] / "dbt"
MODEL = DBT / "models" / "intermediate" / "events"
MODEL /= "int_synthetic_baseline_enrollment_events.sql"


def render(**variables: Any) -> str:
    source = (DBT / "macros" / "deferral_rate_macros.sql").read_text()
    return (
        Environment(undefined=StrictUndefined)
        .from_string(source + MODEL.read_text())
        .render(
            config=lambda **_: "",
            ref=lambda name: name,
            var=lambda name, default=None: variables.get(name, default),
        )
    )


def test_census_rates_are_used_unchanged() -> None:
    rates = [0.06, 0.75, 0.95, 1.0]
    with duckdb.connect() as conn:
        conn.execute("""
            CREATE TABLE int_baseline_workforce (
                employee_id VARCHAR, simulation_year INTEGER,
                employee_deferral_rate DECIMAL(7,5), employee_enrollment_date DATE,
                is_enrolled_at_census BOOLEAN, current_age INTEGER,
                current_tenure INTEGER, level_id INTEGER,
                current_compensation DOUBLE)
            """)
        conn.executemany(
            "INSERT INTO int_baseline_workforce"
            " VALUES (?, 2025, ?, '2020-01-01', true, 40, 5, 1, 80000)",
            [[f"E{i}", rate] for i, rate in enumerate(rates)],
        )
        rows = conn.execute(
            f"SELECT employee_deferral_rate, typeof(employee_deferral_rate),"
            f" data_quality_flag FROM ({render(start_year=2025)}) ORDER BY 1"
        ).fetchall()
    assert [row[0] for row in rows] == rates
    # DOUBLE, as before: fct_yearly_events.employee_deferral_rate keeps its type.
    assert {row[1] for row in rows} == {"DOUBLE"}
    assert {row[2] for row in rows} == {"census_rate_preserved"}
