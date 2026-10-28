"""Execute the contribution model against controlled earned-pay and window inputs."""

from datetime import date
from pathlib import Path

import duckdb
import pytest
from jinja2 import Environment

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]

# (event_type, effective_date, employee_deferral_rate, prev_employee_deferral_rate)
RateEvent = tuple[str, str, float, float | None]


def _render_model() -> str:
    source = ROOT / "dbt/models/intermediate/int_employee_contributions.sql"
    return (
        Environment()
        .from_string(
            (ROOT / "dbt/macros/irs_402g_limit_for_age.sql").read_text()
            + (ROOT / "dbt/macros/deferral_change.sql").read_text()
            + source.read_text()
        )
        .render(
            config=lambda **kwargs: "",
            var=lambda name, default=None: default,
            ref=lambda name: name,
            evt_enrollment=lambda: "'enrollment'",
            evt_deferral_change=lambda: "'deferral_change'",
            evt_enrollment_change=lambda: "'enrollment_change'",
            is_enrollment_event=lambda column: f"{column} IN ('enrollment', 'enrollment_change')",
            is_incremental=lambda: False,
        )
    )


def _run_contributions(
    hire: str,
    termination: str | None,
    earned: int,
    year_end_rate: float,
    events_sql: list[tuple[str, list[object]]],
) -> tuple:
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
            "'e' employee_id, 'p' plan_design_id, 'default' scenario_id, 2025 simulation_year, "
            "?::DOUBLE current_deferral_rate, 'valid' data_quality_flag",
            [year_end_rate],
        )
        conn.execute(
            "CREATE TABLE int_enrollment_state_accumulator AS SELECT "
            "'e' employee_id, 'default' scenario_id, 2025 simulation_year, TRUE is_enrolled"
        )
        conn.execute(
            "CREATE TABLE fct_yearly_events (employee_id VARCHAR, simulation_year INTEGER, "
            "event_type VARCHAR, effective_date DATE, event_details VARCHAR, "
            "event_category VARCHAR, scenario_id VARCHAR DEFAULT 'default', "
            "plan_design_id VARCHAR DEFAULT 'p', event_id VARCHAR, "
            "employee_deferral_rate DOUBLE, prev_employee_deferral_rate DOUBLE)"
        )
        for statement, params in events_sql:
            conn.execute(statement, params)
        conn.execute(f"CREATE TABLE result AS {_render_model()}")
        return conn.execute(
            "SELECT current_compensation, prorated_annual_compensation, "
            "total_contribution_base_compensation, annual_contribution_amount, "
            "effective_annual_deferral_rate FROM result"
        ).fetchone()


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
@pytest.mark.parametrize("new_rate", [None, 0.09, 0.03, 0.0])
def test_earned_pay_and_enrollment_window(
    hire: str,
    termination: str | None,
    earned: int,
    window: bool,
    expected: float,
    new_rate: float | None,
) -> None:
    events: list[tuple[str, list[object]]] = []
    if window:
        events.append(
            (
                "INSERT INTO fct_yearly_events "
                "(employee_id, simulation_year, event_type, effective_date, event_details) VALUES "
                "('e', 2025, 'enrollment', '2025-07-01', '6% deferral'), "
                "('e', 2025, 'enrollment_change', '2025-07-31', 'opt-out')",
                [],
            )
        )
    if new_rate is not None:
        # Earlier and tied rows must not duplicate contributions or win selection.
        events.append(
            (
                "INSERT INTO fct_yearly_events "
                "(employee_id, simulation_year, event_type, effective_date, event_id, "
                "employee_deferral_rate, prev_employee_deferral_rate) VALUES "
                "('e', 2025, 'deferral_change', '2025-07-01', 'z', 0.15, 0.06), "
                "('e', 2025, 'deferral_change', '2025-08-01', 'a', 0.12, 0.06), "
                "('e', 2025, 'deferral_change', '2025-08-01', 'b', ?, 0.06)",
                [new_rate],
            )
        )
    year_end_rate = 0.06 if new_rate is None else new_rate
    row = _run_contributions(hire, termination, earned, year_end_rate, events)
    assert row[0] == 120000
    assert row[1] == earned
    assert float(row[2]) == pytest.approx(expected, abs=0.005)
    rate = 0.06
    if new_rate is not None and not window:
        start = max(date.fromisoformat(hire), date(2025, 1, 1))
        end = date.fromisoformat(termination) if termination else date(2025, 12, 31)
        employed = (end - start).days + 1
        before = (date(2025, 8, 1) - start).days
        rate = (0.06 * before + new_rate * (employed - before)) / employed
    assert float(row[3]) == pytest.approx(expected * rate, abs=0.005)


@pytest.mark.parametrize(
    "hire,timeline,expected_rate,year_end_rate",
    [
        # September enrollee contributes for ~4 months (122 of 365 days).
        (
            "2020-01-01",
            [("enrollment", "2025-09-01", 0.06, None)],
            0.06 * 122 / 365,
            0.06,
        ),
        # 07-01 escalation weights old and new rates ~50/50.
        (
            "2020-01-01",
            [("deferral_escalation", "2025-07-01", 0.07, 0.06)],
            (0.06 * 181 + 0.07 * 184) / 365,
            0.07,
        ),
        # Enrollment then escalation composes 0 -> 6% -> 7%.
        (
            "2020-01-01",
            [
                ("enrollment", "2025-03-01", 0.06, None),
                ("deferral_escalation", "2025-07-01", 0.07, 0.06),
            ],
            (0.06 * 122 + 0.07 * 184) / 365,
            0.07,
        ),
        # Jan 1 escalation (the default) is unchanged: zero days at the old rate.
        ("2020-01-01", [("deferral_escalation", "2025-01-01", 0.07, 0.06)], 0.07, 0.07),
        # A prior-year participant who opts out mid-year contributes until the opt-out.
        (
            "2020-01-01",
            [("enrollment_change", "2025-07-01", 0.0, 0.06)],
            0.06 * 181 / 365,
            0.0,
        ),
        # Mid-year hire enrolling after the AE window: zero until enrollment.
        (
            "2025-07-01",
            [("enrollment", "2025-08-01", 0.06, None)],
            0.06 * 153 / 184,
            0.06,
        ),
        # A Jan 1 match response sets the rate before an escalation generated from
        # the pre-response rate; the accumulator keeps the response rate at year end.
        (
            "2020-01-01",
            [
                ("deferral_match_response", "2025-01-01", 0.06, 0.08),
                ("deferral_escalation", "2025-07-01", 0.09, 0.08),
            ],
            0.06,
            0.06,
        ),
    ],
)
def test_piecewise_rate_timeline(
    hire: str,
    timeline: list[RateEvent],
    expected_rate: float,
    year_end_rate: float,
) -> None:
    events: list[tuple[str, list[object]]] = [
        (
            "INSERT INTO fct_yearly_events (employee_id, simulation_year, event_type, "
            "effective_date, event_id, employee_deferral_rate, prev_employee_deferral_rate) "
            "VALUES ('e', 2025, ?, ?::DATE, ?, ?, ?)",
            [event_type, effective, f"ev{i}", rate, prev],
        )
        for i, (event_type, effective, rate, prev) in enumerate(timeline)
    ]
    earned = 105000 if hire < "2025-01-01" else 52000
    row = _run_contributions(hire, None, earned, year_end_rate, events)
    assert float(row[4]) == pytest.approx(expected_rate, abs=1e-9)
    assert float(row[3]) == pytest.approx(earned * expected_rate, abs=0.005)
