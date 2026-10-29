"""Check the decision-year contract across the rendered helper and compensation SQL."""

from pathlib import Path

import duckdb
import jinja2
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _render(model: str) -> str:
    source = (ROOT / "dbt/models/intermediate" / model).read_text()
    environment = jinja2.Environment(undefined=jinja2.StrictUndefined)
    return environment.from_string(source).render(
        config=lambda **_: "",
        var=lambda name, default=None: {
            "simulation_year": 2026,
            "start_year": 2025,
        }.get(name, default),
        source=lambda _, name: (
            "prior_state"
            if name == "workforce_state_projection"
            else "enrollment_state"
        ),
        ref=lambda *_: "helper",
        assign_age_band=lambda value: f"CASE WHEN {value} < 18 THEN 'under_18' ELSE 'adult' END",
        assign_tenure_band=lambda value: f"CASE WHEN {value} < 5 THEN 'under_5' ELSE 'five_plus' END",
        is_incremental=lambda: False,
    )


@pytest.mark.fast
@pytest.mark.dbt
def test_subsequent_year_compensation_advances_prior_state_once() -> None:
    connection = duckdb.connect(":memory:")
    connection.execute("""CREATE TABLE prior_state AS SELECT
          'e1' AS employee_id, 'ssn' AS employee_ssn,
          DATE '2008-01-01' AS employee_birth_date,
          DATE '2021-01-01' AS employee_hire_date,
          60000 AS full_year_equivalent_compensation,
          17 AS current_age, 4 AS current_tenure, 1 AS level_id,
          NULL::DATE AS enrollment_date,
          NULL::DATE AS authoritative_enrollment_date,
          40 AS scheduled_hours_per_week, 2026 AS decision_year,
          2025 AS source_simulation_year, 'default' AS scenario_id,
          'active' AS employment_status, 60000 AS current_compensation,
          'default' AS plan_design_id""")
    connection.execute("""CREATE TABLE enrollment_state AS SELECT
          'e1' AS employee_id, 2026 AS decision_year,
          'default' AS scenario_id, 'default' AS plan_design_id,
          NULL::DATE AS authoritative_enrollment_date,
          NULL::DATE AS enrollment_date""")
    connection.execute(
        f"CREATE VIEW helper AS {_render('int_active_employees_prev_year_snapshot.sql')}"
    )
    result = connection.execute(
        f"SELECT current_age, current_tenure, age_band, tenure_band "
        f"FROM ({_render('int_employee_compensation_by_year.sql')})"
    ).fetchone()
    assert result == (18, 5, "adult", "five_plus")
