"""Execute the contribution model against controlled earned-pay and window inputs."""

from pathlib import Path

import duckdb
import pytest
from jinja2 import Environment

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "hire,termination,earned,window,expected",
    [
        ("2020-01-01", None, 105000, False, 105000),
        ("2025-07-01", None, 52000, False, 52000),
        ("2020-01-01", "2025-09-30", 78000, False, 78000),
        ("2025-07-01", None, 52000, True, 8760.87),
        ("2025-07-01", "2025-09-30", 26000, True, 8760.87),
    ],
)
def test_earned_pay_and_enrollment_window(
    hire: str,
    termination: str | None,
    earned: int,
    window: bool,
    expected: float,
) -> None:
    source = ROOT / "dbt/models/intermediate/int_employee_contributions.sql"
    sql = (
        Environment()
        .from_string(source.read_text())
        .render(
            config=lambda **kwargs: "",
            var=lambda name, default=None: default,
            ref=lambda name: name,
            evt_enrollment=lambda: "'enrollment'",
            evt_enrollment_change=lambda: "'enrollment_change'",
            is_enrollment_event=lambda column: f"{column} IN ('enrollment', 'enrollment_change')",
            is_incremental=lambda: False,
        )
    )
    with duckdb.connect() as conn:
        conn.execute(
            "CREATE TABLE int_workforce_state_accumulator AS SELECT "
            "'e' employee_id, 'default' scenario_id, 'p' plan_design_id, "
            "2025 simulation_year, 120000 current_compensation, "
            "? prorated_annual_compensation, ?::DATE employee_hire_date, "
            "?::DATE termination_date, 'active' employment_status, "
            "'1990-01-01'::DATE employee_birth_date, 35 current_age",
            [earned, hire, termination],
        )
        conn.execute(
            "CREATE TABLE config_irs_limits AS SELECT 2025 limit_year, "
            "23500 base_limit, 31000 catch_up_limit, 50 catch_up_age_threshold, "
            "34750 super_catch_up_limit, 60 super_catch_up_age_min, 63 super_catch_up_age_max"
        )
        conn.execute(
            "CREATE TABLE int_deferral_rate_state_accumulator AS SELECT "
            "'e' employee_id, 'default' scenario_id, 2025 simulation_year, "
            "0.06 current_deferral_rate, 'valid' data_quality_flag"
        )
        conn.execute(
            "CREATE TABLE int_enrollment_state_accumulator AS SELECT "
            "'e' employee_id, 'default' scenario_id, 2025 simulation_year, TRUE is_enrolled"
        )
        conn.execute(
            "CREATE TABLE fct_yearly_events (employee_id VARCHAR, simulation_year INTEGER, "
            "event_type VARCHAR, effective_date DATE, event_details VARCHAR)"
        )
        if window:
            conn.execute(
                "INSERT INTO fct_yearly_events VALUES "
                "('e', 2025, 'enrollment', '2025-07-01', '6% deferral'), "
                "('e', 2025, 'enrollment_change', '2025-07-31', 'opt-out')"
            )
        conn.execute(f"CREATE TABLE result AS {sql}")
        row = conn.execute(
            "SELECT current_compensation, prorated_annual_compensation, "
            "total_contribution_base_compensation, annual_contribution_amount FROM result"
        ).fetchone()
    assert row[0] == 120000
    assert row[1] == earned
    assert float(row[2]) == pytest.approx(expected, abs=0.005)
    assert float(row[3]) == pytest.approx(expected * 0.06, abs=0.005)
