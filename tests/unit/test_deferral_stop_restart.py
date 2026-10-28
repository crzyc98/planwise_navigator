"""Stop/restart lifecycle through the real generator, accumulator and contributions."""

from datetime import date
from typing import Any

import duckdb
import pytest

from tests.unit.test_deferral_changes import (
    DBT,
    STATE_MODEL,
    conn as connection_fixture,
    event_sql,
    fixture_inputs,
    render,
)

pytestmark = pytest.mark.fast
conn = connection_fixture


def stop_settings(**overrides: Any) -> dict[str, Any]:
    return {
        "deferral_rate_changes_enabled": True,
        "deferral_rate_changes_with_escalation_increase_probability": 0.0,
        "deferral_rate_changes_with_escalation_decrease_probability": 0.0,
        "deferral_rate_changes_without_escalation_increase_probability": 0.0,
        "deferral_rate_changes_without_escalation_decrease_probability": 0.0,
        "deferral_rate_changes_stop_probability": 1.0,
        "deferral_rate_changes_restart_probability": 1.0,
    } | overrides


def accumulate(
    connection: duckdb.DuckDBPyConnection, year: int, **variables: Any
) -> None:
    prefix = (
        "CREATE TABLE int_deferral_rate_state_accumulator AS "
        if year == 2025
        else "INSERT INTO int_deferral_rate_state_accumulator "
    )
    connection.execute(
        prefix
        + render((DBT / STATE_MODEL).read_text(), simulation_year=year, **variables)
    )


def publish(connection: duckdb.DuckDBPyConnection, year: int, **variables: Any) -> None:
    prefix = (
        "CREATE TABLE fct_yearly_events AS "
        if year == 2025
        else "INSERT INTO fct_yearly_events BY NAME "
    )
    connection.execute(
        prefix + "SELECT *, 'default' AS scenario_id, 'default' AS plan_design_id, "
        "employee_id || '-change-' || simulation_year AS event_id FROM ("
        + event_sql(year, **variables)
        + ")"
    )


def stopped_fixture(connection: duckdb.DuckDBPyConnection) -> None:
    fixture_inputs(connection)
    connection.execute("""INSERT INTO int_enrollment_events
      VALUES ('employee-0', 'default', 2025, 'enrollment_change', DATE '2025-08-01', 0, 'opt-out',
        'enrollment_opt_out')""")
    publish(connection, 2025, **stop_settings())
    connection.execute("""
      ALTER TABLE fct_yearly_events ALTER COLUMN effective_date TYPE TIMESTAMP;
      INSERT INTO fct_yearly_events BY NAME SELECT *, 'default' AS plan_design_id
        FROM int_enrollment_events;
      INSERT INTO fct_yearly_events BY NAME
        SELECT employee_id, simulation_year, effective_date, 'deferral_escalation' AS event_type,
          'default' AS scenario_id, 'default' AS plan_design_id,
          new_deferral_rate AS employee_deferral_rate,
          previous_deferral_rate AS prev_employee_deferral_rate
        FROM int_deferral_rate_escalation_events
    """)
    accumulate(connection, 2025, **stop_settings())


def advance(connection: duckdb.DuckDBPyConnection, year: int) -> None:
    for table in (
        "int_employee_compensation_by_year",
        "int_plan_design_assignment_accumulator",
        "int_employee_termination_dates",
    ):
        connection.execute(f"UPDATE {table} SET simulation_year = ?", [year])


def assert_contract(
    connection: duckdb.DuckDBPyConnection, year: int, **variables: Any
) -> None:
    assert (
        connection.execute(
            render(
                (DBT / "tests/assert_deferral_change_previous_rate.sql").read_text(),
                simulation_year=year,
                **variables,
            )
        ).fetchall()
        == []
    )


def contributions(connection: duckdb.DuckDBPyConnection, year: int) -> list[tuple]:
    connection.execute("""CREATE OR REPLACE TABLE int_workforce_state_accumulator AS
      SELECT employee_id, 'default' AS scenario_id, 'default' AS plan_design_id,
        simulation_year, employee_compensation AS current_compensation,
        employee_compensation AS prorated_annual_compensation,
        DATE '2020-01-01' AS employee_hire_date, NULL::DATE AS termination_date,
        employment_status, employee_birth_date, current_age
      FROM int_employee_compensation_by_year;
      CREATE OR REPLACE TABLE int_enrollment_state_accumulator AS
      SELECT employee_id, scenario_id, simulation_year, is_enrolled_flag AS is_enrolled
      FROM int_deferral_rate_state_accumulator""")
    connection.execute(
        "CREATE OR REPLACE TABLE contributions AS "
        + render(
            (DBT / "models/intermediate/int_employee_contributions.sql").read_text(),
            simulation_year=year,
            deferral_rate_changes_enabled=True,
        )
    )
    return connection.execute("""SELECT c.annual_contribution_amount,
        c.effective_annual_deferral_rate, e.effective_date
      FROM contributions c JOIN fct_yearly_events e USING (employee_id, simulation_year)
      WHERE e.event_type = 'deferral_change' ORDER BY employee_id""").fetchall()


@pytest.mark.parametrize(
    "caps,restored",
    [
        ({}, 0.09),
        ({"voluntary_max_deferral_rate": 0.05}, 0.05),
        ({"plan_deferral_cap": 0.04}, 0.04),
    ],
)
def test_stop_restart_weighting_and_carry(
    conn: duckdb.DuckDBPyConnection, caps: dict[str, float], restored: float
) -> None:
    stopped_fixture(conn)
    assert_contract(conn, 2025)
    assert conn.execute("""SELECT COUNT(*) FROM int_deferral_rate_state_accumulator
      WHERE current_deferral_rate = 0 AND is_enrolled_flag
        AND last_nonzero_deferral_rate = .09""").fetchone()[0] == 99
    stop_rows = contributions(conn, 2025)
    assert len(stop_rows) == 99
    for amount, rate, effective in stop_rows:
        # Timeline: 6% until the July 1 escalation, 7% until the stop, then 0.
        expected = (
            0.06 * 181 + 0.07 * (effective.date() - date(2025, 7, 1)).days
        ) / 365
        assert float(amount) == pytest.approx(50000 * expected, abs=0.005)
        assert float(rate) == pytest.approx(expected, abs=0.000001)
    advance(conn, 2026)
    variables = stop_settings(**caps)
    publish(conn, 2026, **variables)
    accumulate(conn, 2026, **variables)
    assert_contract(conn, 2026, **variables)
    restart_rows = contributions(conn, 2026)
    assert len(restart_rows) == 99
    for amount, rate, effective in restart_rows:
        expected = restored * (date(2027, 1, 1) - effective.date()).days / 365
        assert float(amount) == pytest.approx(50000 * expected, abs=0.005)
        assert float(rate) == pytest.approx(expected, abs=0.000001)
    advance(conn, 2027)
    accumulate(conn, 2027, **variables)
    assert (
        conn.execute(
            """SELECT COUNT(*) FROM int_deferral_rate_state_accumulator
      WHERE simulation_year = 2027 AND current_deferral_rate = ?
        AND last_nonzero_deferral_rate = ? AND is_enrolled_flag""",
            [restored, restored],
        ).fetchone()[0]
        == 99
    )
    assert (
        conn.execute(
            """SELECT COUNT(*) FROM fct_yearly_events
      WHERE employee_id = 'employee-0' AND event_type = 'deferral_change'"""
        ).fetchone()[0]
        == 0
    )


@pytest.mark.parametrize(
    "reason",
    ["no_stop", "optout_after", "optout_same_day", "not_enrolled", "zero_census"],
)
def test_restart_requires_stop_provenance(
    conn: duckdb.DuckDBPyConnection, reason: str
) -> None:
    stopped_fixture(conn)
    if reason == "no_stop":
        conn.execute("DELETE FROM fct_yearly_events WHERE event_category = 'stop'")
    elif reason.startswith("optout"):
        offset = 1 if reason == "optout_after" else 0
        conn.execute(f"""INSERT INTO fct_yearly_events BY NAME
          SELECT employee_id, scenario_id, plan_design_id, simulation_year,
            effective_date + INTERVAL '{offset} days' AS effective_date,
            'enrollment_change' AS event_type, 0 AS employee_deferral_rate
          FROM fct_yearly_events WHERE event_category = 'stop'""")
    elif reason == "not_enrolled":
        conn.execute(
            "UPDATE int_deferral_rate_state_accumulator SET is_enrolled_flag = FALSE"
        )
    else:
        conn.execute("UPDATE int_baseline_workforce SET employee_deferral_rate = 0")
        assert conn.execute(event_sql(**stop_settings())).fetchall() == []
        return
    advance(conn, 2026)
    assert conn.execute(event_sql(2026, **stop_settings())).fetchall() == []


def test_stopped_participants_cannot_increase_decrease_stop_or_escalate(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    stopped_fixture(conn)
    advance(conn, 2026)
    for increase, decrease, stop in [(1, 0, 0), (0, 1, 0), (0, 0, 1)]:
        assert (
            conn.execute(
                event_sql(
                    2026,
                    **stop_settings(
                        deferral_rate_changes_with_escalation_increase_probability=increase,
                        deferral_rate_changes_with_escalation_decrease_probability=decrease,
                        deferral_rate_changes_stop_probability=stop,
                        deferral_rate_changes_restart_probability=0,
                    ),
                )
            ).fetchall()
            == []
        )
    conn.execute(
        """ALTER TABLE int_employee_compensation_by_year ADD COLUMN employee_hire_date DATE
        DEFAULT DATE '2020-01-01';
      CREATE TABLE int_synthetic_baseline_enrollment_events AS
        SELECT employee_id, employee_deferral_rate, employee_enrollment_date AS effective_date
        FROM int_baseline_workforce;
      ALTER TABLE int_enrollment_events ADD COLUMN IF NOT EXISTS event_category VARCHAR"""
    )
    assert (
        conn.execute(
            render(
                (
                    DBT
                    / "models/intermediate/events/int_deferral_rate_escalation_events.sql"
                ).read_text(),
                simulation_year=2026,
                deferral_rate_changes_enabled=True,
            )
        ).fetchall()
        == []
    )


def test_stop_band_preserves_increase_decrease_payloads(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    fixture_inputs(conn)
    variables = {
        "deferral_rate_changes_with_escalation_increase_probability": 0.25,
        "deferral_rate_changes_with_escalation_decrease_probability": 0.075,
    }
    before = conn.execute(event_sql(**variables)).fetchall()
    after = conn.execute(
        event_sql(**variables, deferral_rate_changes_stop_probability=0.5)
    ).fetchall()
    assert [r for r in after if r[-1] != "stop"] == before
    assert any(r[-1] == "stop" for r in after)
    rows = conn.execute(
        render(
            """SELECT {{ deferral_change_category('u', '.25', '.075', 'FALSE', '.015') }}
      FROM (VALUES (.324999), (.325), (.339999), (.340)) t(u) ORDER BY u"""
        )
    ).fetchall()
    assert rows == [("proactive_decrease",), ("stop",), ("stop",), (None,)]


@pytest.mark.parametrize(
    "mutation", ["no_stop", "later_optout", "current_optout", "wrong_rate", "duplicate"]
)
def test_restart_singular_guard(conn: duckdb.DuckDBPyConnection, mutation: str) -> None:
    stopped_fixture(conn)
    advance(conn, 2026)
    publish(conn, 2026, **stop_settings())
    accumulate(conn, 2026, **stop_settings())
    assert_contract(conn, 2026)
    mutations = {
        "no_stop": "DELETE FROM fct_yearly_events WHERE event_category = 'stop'",
        "later_optout": "INSERT INTO fct_yearly_events BY NAME SELECT employee_id, scenario_id, plan_design_id, 2025 AS simulation_year, DATE '2025-12-31' AS effective_date, 'enrollment_change' AS event_type, 0 AS employee_deferral_rate FROM fct_yearly_events WHERE event_category = 'restart'",
        "current_optout": "INSERT INTO fct_yearly_events BY NAME SELECT employee_id, scenario_id, plan_design_id, simulation_year, DATE '2026-01-01' AS effective_date, 'enrollment_change' AS event_type, 0 AS employee_deferral_rate FROM fct_yearly_events WHERE event_category = 'restart'",
        "wrong_rate": "UPDATE fct_yearly_events SET employee_deferral_rate = .08 WHERE event_category = 'restart'; UPDATE int_deferral_rate_state_accumulator SET current_deferral_rate = .08 WHERE simulation_year = 2026",
        "duplicate": "INSERT INTO fct_yearly_events SELECT * FROM fct_yearly_events WHERE event_category = 'restart'",
    }
    conn.execute(mutations[mutation])
    rows = conn.execute(
        render(
            (DBT / "tests/assert_deferral_change_previous_rate.sql").read_text(),
            simulation_year=2026,
        )
    ).fetchall()
    assert len(rows) == (198 if mutation == "duplicate" else 99)


def test_waiting_stopper_retains_rate_and_restarts_at_current_irs_cap(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    stopped_fixture(conn)
    advance(conn, 2026)
    publish(conn, 2026, **stop_settings(deferral_rate_changes_restart_probability=0))
    accumulate(conn, 2026, **stop_settings())
    assert (
        conn.execute("""SELECT COUNT(*) FROM int_deferral_rate_state_accumulator
      WHERE simulation_year = 2026 AND current_deferral_rate = 0
        AND last_nonzero_deferral_rate = .09 AND is_enrolled_flag""").fetchone()[0]
        == 99
    )
    advance(conn, 2027)
    conn.execute(
        "UPDATE int_employee_compensation_by_year SET employee_compensation = 400000"
    )
    publish(conn, 2027, **stop_settings())
    accumulate(conn, 2027, **stop_settings())
    assert_contract(conn, 2027)
    assert (
        conn.execute("""SELECT COUNT(*) FROM int_deferral_rate_state_accumulator
      WHERE simulation_year = 2027 AND current_deferral_rate = .0587
        AND last_nonzero_deferral_rate = .0587 AND is_enrolled_flag""").fetchone()[0]
        == 99
    )


@pytest.mark.parametrize("group", ["with_escalation", "without_escalation"])
def test_stop_band_cannot_be_truncated_by_other_probabilities(group: str) -> None:
    from pydantic import ValidationError
    from planalign_orchestrator.config.participant_behavior import (
        DeferralRateChangesSettings,
    )

    settings = {group: {"increase_probability": 0.9, "decrease_probability": 0.1}}
    with pytest.raises(ValidationError, match="increase, decrease and stop"):
        DeferralRateChangesSettings(enabled=True, **settings)
    DeferralRateChangesSettings(enabled=True, stop_probability=0, **settings)
    DeferralRateChangesSettings(enabled=False, **settings)


@pytest.mark.parametrize("category", ["stop", "restart"])
def test_stop_restart_obey_empty_d3_window(
    conn: duckdb.DuckDBPyConnection, category: str
) -> None:
    if category == "stop":
        fixture_inputs(conn)
        conn.execute(
            "UPDATE int_deferral_rate_escalation_events SET effective_date = DATE '2025-12-31'"
        )
        year = 2025
    else:
        stopped_fixture(conn)
        advance(conn, 2026)
        # A current-year zero-rate enrollment election still bounds restart timing.
        conn.execute("""INSERT INTO int_enrollment_events
          SELECT employee_id, 'default', 2026, 'enrollment', DATE '2026-12-31', 0, '',
            'voluntary_enrollment'
          FROM int_baseline_workforce""")
        year = 2026
    assert conn.execute(event_sql(year, **stop_settings())).fetchall() == []


@pytest.mark.parametrize(
    "mutation", [None, "missing_stop", "not_enrolled", "wrong_status", "disabled"]
)
def test_voluntary_persistence_allows_only_documented_enrolled_stop(
    conn: duckdb.DuckDBPyConnection, mutation: str | None
) -> None:
    conn.execute("""CREATE TABLE fct_yearly_events AS
      SELECT 'e' AS employee_id, 'default' AS scenario_id, 2025 AS simulation_year,
        'enrollment' AS event_type, 'voluntary_enrollment' AS event_category, '' AS event_details
      UNION ALL SELECT 'e', 'default', 2026, 'deferral_change', 'stop', '';
      CREATE TABLE fct_workforce_snapshot AS
      SELECT 'e' AS employee_id, 'default' AS scenario_id, 2025 AS simulation_year,
        'participating' AS participation_status, .06 AS current_deferral_rate,
        'active' AS employment_status, TRUE AS is_enrolled_flag,
        'participating - voluntary enrollment' AS participation_status_detail
      UNION ALL SELECT 'e', 'default', 2026, 'not_participating', 0, 'active', TRUE,
        'not_participating - stopped contributions'""")
    if mutation == "missing_stop":
        conn.execute("DELETE FROM fct_yearly_events WHERE event_category = 'stop'")
    elif mutation == "not_enrolled":
        conn.execute(
            "UPDATE fct_workforce_snapshot SET is_enrolled_flag = FALSE WHERE simulation_year = 2026"
        )
    elif mutation == "wrong_status":
        conn.execute(
            "UPDATE fct_workforce_snapshot SET participation_status_detail = 'wrong' WHERE simulation_year = 2026"
        )
    result = conn.execute(
        render(
            (DBT / "tests/assert_voluntary_enrollment_persists.sql").read_text(),
            deferral_rate_changes_enabled=mutation != "disabled",
        )
    ).fetchall()
    assert len(result) == (0 if mutation is None else 1)


@pytest.mark.parametrize(
    "mutation",
    [None, "prior_leaver", "missing_snapshot", "not_enrolled", "wrong_detail"],
)
def test_stopped_snapshot_guard_uses_current_workforce(
    conn: duckdb.DuckDBPyConnection, mutation: str | None
) -> None:
    conn.execute("""CREATE TABLE int_deferral_rate_state_accumulator AS
      SELECT 'e' AS employee_id, 'default' AS scenario_id, 'default' AS plan_design_id,
        2026 AS simulation_year, 0 AS current_deferral_rate, TRUE AS is_enrolled_flag;
      CREATE TABLE int_workforce_state_accumulator AS
        SELECT employee_id, scenario_id, plan_design_id, simulation_year
        FROM int_deferral_rate_state_accumulator;
      CREATE TABLE fct_workforce_snapshot AS
        SELECT *, 'not_participating' AS participation_status,
          'not_participating - stopped contributions' AS participation_status_detail
        FROM int_deferral_rate_state_accumulator;
      CREATE TABLE fct_yearly_events AS
        SELECT employee_id, scenario_id, 2025 AS simulation_year,
          'deferral_change' AS event_type, 'stop' AS event_category,
          0 AS employee_deferral_rate, DATE '2025-07-01' AS effective_date
        FROM int_deferral_rate_state_accumulator""")
    if mutation in ("prior_leaver", "missing_snapshot"):
        conn.execute("DELETE FROM fct_workforce_snapshot")
    if mutation == "prior_leaver":
        conn.execute("DELETE FROM int_workforce_state_accumulator")
    elif mutation == "not_enrolled":
        conn.execute("UPDATE fct_workforce_snapshot SET is_enrolled_flag = FALSE")
    elif mutation == "wrong_detail":
        conn.execute(
            "UPDATE fct_workforce_snapshot SET participation_status_detail = 'wrong'"
        )
    rows = conn.execute(
        render(
            (DBT / "tests/assert_stopped_participation.sql").read_text(),
            simulation_year=2026,
            deferral_rate_changes_enabled=True,
        )
    ).fetchall()
    assert len(rows) == (0 if mutation in (None, "prior_leaver") else 1)
