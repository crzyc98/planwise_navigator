"""Execute voluntary change macros and the real event/accumulator SQL in DuckDB."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
from jinja2 import Environment, StrictUndefined
import pytest
from pydantic import ValidationError

from planalign_orchestrator.config.participant_behavior import (
    DeferralRateChangesSettings,
)

pytestmark = pytest.mark.fast
DBT = Path(__file__).resolve().parents[2] / "dbt"
EVENT_MODEL = "models/intermediate/events/int_deferral_change_events.sql"
STATE_MODEL = "models/intermediate/int_deferral_rate_state_accumulator.sql"
MACROS = (
    "reenrollment_sweep.sql",
    "utils/subsystem_seed.sql",
    "utils/stable_decimal.sql",
    "constants.sql",
    "self_directed_enrollment_rate.sql",
    "aip_initial_membership.sql",
    "easy_enroll.sql",
    "get_plan_design_parameters.sql",
    "irs_402g_limit_for_age.sql",
    "deferral_rate_macros.sql",
    "deferral_change.sql",
)


def render(source: str, **variables: Any) -> str:
    """Stub dbt plumbing only; rate, draw, timing and state logic is production SQL."""
    macros = "\n".join((DBT / "macros" / name).read_text() for name in MACROS)
    return (
        Environment(undefined=StrictUndefined)
        .from_string(macros + source)
        .render(
            var=lambda name, default=None: variables.get(name, default),
            ref=lambda name: name,
            config=lambda **kwargs: "",
            is_incremental=lambda: False,
            this="int_deferral_rate_state_accumulator",
            target={"schema": "main"},
            assign_age_band=lambda column: "'35-44'",
            assign_tenure_band=lambda column: "'0-4'",
        )
    )


@pytest.fixture
def conn() -> Iterator[duckdb.DuckDBPyConnection]:
    with duckdb.connect() as connection:
        module = (
            Environment()
            .from_string((DBT / "macros/utils/stable_hash.sql").read_text())
            .module
        )
        connection.execute(getattr(module, "install_stable_hash")())
        yield connection


@pytest.mark.parametrize("escalated", [False, True])
def test_probability_boundaries(
    conn: duckdb.DuckDBPyConnection, escalated: bool
) -> None:
    rows = conn.execute(
        render(
            """
      SELECT u, {{ deferral_change_category('u', '0.25', '0.075', var('escalated', false)) }}
      FROM (VALUES (0.0), (0.249999), (0.25), (0.324999), (0.325), (0.999999)) t(u)
      ORDER BY u
    """,
            escalated=escalated,
        )
    ).fetchall()
    assert [row[1] for row in rows] == [
        "proactive_increase",
        "proactive_increase",
        "aip_response_decrease" if escalated else "proactive_decrease",
        "aip_response_decrease" if escalated else "proactive_decrease",
        None,
        None,
    ]


@pytest.mark.parametrize("direction", ["increase", "decrease"])
def test_weight_boundaries(conn: duckdb.DuckDBPyConnection, direction: str) -> None:
    sql = "SELECT {{ deferral_change_step('u', '" + direction + "') }} "
    sql += "FROM (VALUES (0.0), (0.199999), (0.2), (0.999999)) t(u) ORDER BY u"
    variables = {
        f"deferral_rate_changes_{direction}_steps": [
            {"pp": 1, "weight": 0.2},
            {"pp": 9, "weight": 0.8},
        ]
    }
    assert conn.execute(render(sql, **variables)).fetchall() == [(1,), (1,), (9,), (9,)]


def test_draws_probabilities_weights_and_seed(conn: duckdb.DuckDBPyConnection) -> None:
    sql = """
      WITH draws AS (
        SELECT {{ enrollment_behavior_draw('CAST(i AS VARCHAR)', 2025, '-deferral-change-') }} AS u,
          {{ enrollment_behavior_draw('CAST(i AS VARCHAR)', 2025, '-deferral-change-step-') }} AS s,
          {{ enrollment_behavior_draw('CAST(i AS VARCHAR)', 2025, '-deferral-change-timing-') }} AS t
        FROM range({{ var('draws', 20000) }}) r(i)
      )
      SELECT {{ deferral_change_category('u', '0.25', '0.075', var('escalated', false)) }} AS category,
        {{ deferral_change_step('s', 'increase') }} AS step, COUNT(*), AVG(t)
      FROM draws GROUP BY ALL ORDER BY ALL
    """
    rows = conn.execute(render(sql)).fetchall()
    # The hash draws are costly in SQL; a smaller sample proves determinism.
    sample = conn.execute(render(sql, draws=2000)).fetchall()
    assert sample == conn.execute(render(sql, draws=2000)).fetchall()
    assert (
        sample
        != conn.execute(
            render(sql, draws=2000, random_seed_deferral_behavior=43)
        ).fetchall()
    )
    for category, expected in [
        ("proactive_increase", 0.25),
        ("proactive_decrease", 0.075),
    ]:
        total = sum(n for c, _, n, _ in rows if c == category)
        assert total / 20000 == pytest.approx(expected, abs=0.01)
        for step, weight in [
            (1, 0.10),
            (2, 0.10),
            (3, 0.15),
            (5, 0.20),
            (7, 0.20),
            (10, 0.25),
        ]:
            n = next(n for c, pp, n, _ in rows if c == category and pp == step)
            assert n / total == pytest.approx(weight, abs=0.04)
    assert all(mean == pytest.approx(0.5, abs=0.07) for _, _, _, mean in rows)


@pytest.mark.parametrize(
    "before,category,step,cap,expected",
    [
        (0.005, "proactive_decrease", 1, 0.15, 0.005),
        (0.01, "proactive_decrease", 8, 0.15, 0.01),
        (0.03, "proactive_decrease", 8, 0.15, 0.01),
        (0.07, "proactive_decrease", 2, 0.15, 0.05),
        (0.03, "aip_response_decrease", 8, 0.15, 0.01),
        (0.07, "aip_response_decrease", 2, 0.15, 0.05),
        (0.14, "proactive_increase", 3, 0.15, 0.15),
        (0.16, "proactive_increase", 3, 0.15, 0.16),
        (0.005, "proactive_increase", 1, 0.15, 0.015),
        (0.07, "proactive_increase", 2, 0.0833, 0.0833),
    ],
)
def test_rate_bounds(
    conn: duckdb.DuckDBPyConnection,
    before: float,
    category: str,
    step: int,
    cap: float,
    expected: float,
) -> None:
    sql = "SELECT {{ deferral_change_rate('" + str(before) + "', \"'" + category
    sql += "'\", '" + str(step) + "', '" + str(cap) + "') }}"
    assert float(conn.execute(render(sql)).fetchone()[0]) == expected


@pytest.mark.parametrize(
    "start,end,draw,expected",
    [
        ("2025-01-02", "2025-12-31", 0, "2025-01-02"),
        ("2025-01-02", "2025-12-31", 0.999999, "2025-12-31"),
        ("2025-11-02", "2025-11-05", 0.999999, "2025-11-05"),
        ("2025-12-31", "2025-12-31", 0.5, "2025-12-31"),
        ("2026-01-01", "2025-12-31", 0.5, None),
        ("2025-01-02", "2025-01-01", 0, None),
    ],
)
def test_window_bounds(
    conn: duckdb.DuckDBPyConnection,
    start: str,
    end: str,
    draw: float,
    expected: str | None,
) -> None:
    sql = "SELECT {{ deferral_change_date(\"DATE '" + start + "'\", \"DATE '" + end
    sql += "'\", '" + str(draw) + "') }}"
    result = conn.execute(render(sql)).fetchone()[0]
    assert (str(result) if result else None) == expected


@pytest.mark.parametrize(
    "age,comp,expected",
    [
        (40, 400000, 0.0587),
        (50, 400000, 0.0775),
        (61, 400000, 0.0868),
        (40, 50000, 0.15),
        (40, 0, 0.15),
    ],
)
def test_irs_cap(
    conn: duckdb.DuckDBPyConnection, age: int, comp: int, expected: float
) -> None:
    sql = "SELECT {{ deferral_change_cap('" + str(comp) + "', '" + str(age) + "') }} "
    sql += "FROM (SELECT 23500 base_limit, 31000 catch_up_limit, 50 catch_up_age_threshold, "
    sql += "34750 super_catch_up_limit, 60 super_catch_up_age_min, 63 super_catch_up_age_max) il"
    assert float(conn.execute(render(sql)).fetchone()[0]) == expected


def fixture_inputs(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
      CREATE TABLE int_baseline_workforce AS
      SELECT 'employee-' || i AS employee_id, DATE '2020-01-01' AS employee_enrollment_date,
        0.06::DECIMAL(5,4) AS employee_deferral_rate, 2025 AS simulation_year FROM range(100) t(i);
      CREATE TABLE stg_census_data AS
      SELECT employee_id, FALSE AS auto_escalation_opt_out FROM int_baseline_workforce;
      CREATE TABLE int_employee_compensation_by_year AS
      SELECT employee_id, 'synthetic' AS employee_ssn, DATE '1985-01-01' AS employee_birth_date,
        50000::DECIMAL(12,2) AS employee_compensation, 40 AS current_age, 5 AS current_tenure,
        1 AS level_id, 'active' AS employment_status, 2025 AS simulation_year
      FROM int_baseline_workforce;
      CREATE TABLE int_plan_design_assignment_accumulator AS
      SELECT employee_id, 'default' AS scenario_id, 'default' AS plan_design_id,
        2025 AS simulation_year FROM int_baseline_workforce;
      CREATE TABLE int_employee_termination_dates AS
      SELECT employee_id, 2025 AS simulation_year, NULL::DATE AS termination_date
      FROM int_baseline_workforce;
      CREATE TABLE config_irs_limits AS
      SELECT 2025 AS limit_year, 23500 AS base_limit, 31000 AS catch_up_limit,
        50 AS catch_up_age_threshold, 34750 AS super_catch_up_limit,
        60 AS super_catch_up_age_min, 63 AS super_catch_up_age_max;
      CREATE TABLE int_deferral_rate_escalation_events AS
      SELECT employee_id, 2025 AS simulation_year, DATE '2025-07-01' AS effective_date,
        .07::DECIMAL(5,4) AS new_deferral_rate, .06::DECIMAL(5,4) AS previous_deferral_rate,
        .01::DECIMAL(5,4) AS escalation_rate, .10::DECIMAL(5,4) AS max_escalation_rate
      FROM int_baseline_workforce;
      CREATE TABLE int_deferral_match_response_events AS
      SELECT employee_id, 2025 AS simulation_year, DATE '2025-01-01' AS effective_date,
        .08::DECIMAL(5,4) AS employee_deferral_rate, .06::DECIMAL(5,4) AS prev_employee_deferral_rate
      FROM int_baseline_workforce;
      CREATE TABLE int_enrollment_events AS
      SELECT employee_id, 'default' AS scenario_id, 2025 AS simulation_year,
        'enrollment' AS event_type, DATE '2025-02-01' AS effective_date,
        .06::DECIMAL(5,4) AS employee_deferral_rate, '' AS event_details, 'auto_enrollment' AS event_category
      FROM int_baseline_workforce WHERE FALSE;
      CREATE TABLE int_reenrollment_sweep_events AS SELECT * FROM int_enrollment_events;
    """)


def event_sql(year: int = 2025, **variables: Any) -> str:
    defaults = {
        "simulation_year": year,
        "deferral_rate_changes_enabled": True,
        "deferral_rate_changes_stop_probability": 0.0,
        "deferral_rate_changes_with_escalation_increase_probability": 0.5,
        "deferral_rate_changes_with_escalation_decrease_probability": 0.5,
        "deferral_rate_changes_increase_steps": [{"pp": 2, "weight": 1}],
        "deferral_rate_changes_decrease_steps": [{"pp": 2, "weight": 1}],
        **{
            f"deferral_rate_changes_multipliers_{direction}_{dimension}": [
                {"min": 0, "multiplier": 1.0}
            ]
            for direction in ("increase", "decrease")
            for dimension in ("age", "income", "tenure")
        },
    }
    return render((DBT / EVENT_MODEL).read_text(), **(defaults | variables))


@pytest.mark.parametrize("leaves", [False, True])
@pytest.mark.parametrize("easy_enroll", [False, True])
def test_real_accumulator_two_year_carry_and_escalation(
    conn: duckdb.DuckDBPyConnection,
    leaves: bool,
    easy_enroll: bool,
) -> None:
    """#983 acceptance: real generated changes -> real state -> next-year state."""
    fixture_inputs(conn)
    variables = {
        "deferral_rate_changes_enabled": True,
        "deferral_rate_changes_post_escalation_decrease_leaves_escalation": leaves,
        "easy_enroll_enabled": easy_enroll,
    }
    conn.execute("CREATE TABLE changes AS " + event_sql())
    conn.execute("""
      CREATE TABLE fct_yearly_events AS
      SELECT *, 'default' AS scenario_id, 'default' AS plan_design_id,
        employee_id || '-change' AS event_id FROM changes;
      INSERT INTO fct_yearly_events BY NAME
      SELECT employee_id, simulation_year, effective_date, 'deferral_escalation' AS event_type,
        new_deferral_rate AS employee_deferral_rate, 'default' AS scenario_id,
        'default' AS plan_design_id FROM int_deferral_rate_escalation_events
    """)
    if easy_enroll:
        conn.execute("""INSERT INTO fct_yearly_events BY NAME
          SELECT employee_id, 'default' AS scenario_id, 'default' AS plan_design_id,
            2024 AS simulation_year, 'enrollment' AS event_type,
            'easy_enroll' AS event_category, DATE '2020-01-01' AS effective_date,
            .06 AS employee_deferral_rate FROM int_baseline_workforce""")
    conn.execute(
        "CREATE TABLE int_deferral_rate_state_accumulator AS "
        + render(
            (DBT / STATE_MODEL).read_text(),
            simulation_year=2025,
            **variables,
        )
    )
    rows = conn.execute("""
      SELECT e.event_category, COUNT(*), MIN(s.rate_before_voluntary_change),
        MIN(s.current_deferral_rate), MIN(s.last_nonzero_deferral_rate),
        BOOL_AND(e.effective_date > DATE '2025-07-01')
      FROM changes e JOIN int_deferral_rate_state_accumulator s USING (employee_id)
      GROUP BY 1 ORDER BY 1
    """).fetchall()
    assert {r[0] for r in rows} == {"aip_response_decrease", "proactive_increase"}
    assert len(rows) == 2 and sum(r[1] for r in rows) == 100
    for category, _, before, after, last_nonzero, ordered in rows:
        assert float(before) == 0.09  # match .08 + escalation .01, NOT escalation .07
        assert float(after) == (0.11 if category == "proactive_increase" else 0.07)
        assert float(last_nonzero) == float(after) and ordered
    assert (
        conn.execute(
            render(
                (DBT / "tests/assert_deferral_change_previous_rate.sql").read_text(),
                simulation_year=2025,
                **variables,
            )
        ).fetchall()
        == []
    )
    for table in (
        "int_employee_compensation_by_year",
        "int_plan_design_assignment_accumulator",
        "int_employee_termination_dates",
    ):
        conn.execute(f"UPDATE {table} SET simulation_year = 2026")
    conn.execute(
        "INSERT INTO int_deferral_rate_state_accumulator "
        + render(
            (DBT / STATE_MODEL).read_text(),
            simulation_year=2026,
            **variables,
        )
    )
    assert conn.execute("""
      SELECT COUNT(*) FROM int_deferral_rate_state_accumulator a
      JOIN int_deferral_rate_state_accumulator b ON a.employee_id = b.employee_id
        AND a.simulation_year = 2025 AND b.simulation_year = 2026
      WHERE a.current_deferral_rate = b.current_deferral_rate
        AND b.rate_before_voluntary_change = a.current_deferral_rate
        AND b.rate_source = 'carried_forward'
    """).fetchone()[0] == 100
    assert (
        conn.execute(
            """
      SELECT COUNT(*) FROM int_deferral_rate_state_accumulator s
      JOIN changes e USING (employee_id)
      WHERE s.aip_participant IS DISTINCT FROM
        (NOT (? AND e.event_category = 'aip_response_decrease'))
    """,
            [leaves],
        ).fetchone()[0]
        == 0
    )
    assert (
        conn.execute(
            render(
                (DBT / "tests/assert_aip_membership.sql").read_text(),
                simulation_year=2026,
                **variables,
            )
        ).fetchall()
        == []
    )
    # Real escalation SQL consumes the persisted membership, including historical EE.
    conn.execute("""
      ALTER TABLE int_employee_compensation_by_year ADD COLUMN employee_hire_date DATE
        DEFAULT DATE '2020-01-01';
      CREATE TABLE int_synthetic_baseline_enrollment_events AS
        SELECT employee_id, employee_deferral_rate,
          employee_enrollment_date AS effective_date FROM int_baseline_workforce
        WHERE employee_id NOT IN (SELECT employee_id FROM fct_yearly_events
          WHERE event_type = 'enrollment');

      INSERT INTO int_enrollment_events BY NAME SELECT employee_id, scenario_id,
        simulation_year, event_type, effective_date, employee_deferral_rate,
        event_category, event_details FROM fct_yearly_events WHERE event_type = 'enrollment'
    """)
    escalation_source = (
        "models/intermediate/events/int_deferral_rate_escalation_events.sql"
    )
    conn.execute(
        "CREATE TABLE next_escalations AS "
        + render(
            (DBT / escalation_source).read_text(), simulation_year=2026, **variables
        )
    )
    responders = next(row[1] for row in rows if row[0] == "aip_response_decrease")
    assert conn.execute("""SELECT COUNT(*) FROM next_escalations e
      JOIN changes c USING (employee_id)
      WHERE c.event_category = 'aip_response_decrease'
    """).fetchone()[0] == (0 if leaves else responders)
    # Generator must also start from carried state, not original census rates.
    conn.execute(
        "CREATE TABLE changes_2026 AS "
        + event_sql(
            2026,
            deferral_rate_changes_without_escalation_increase_probability=1.0,
            deferral_rate_changes_without_escalation_decrease_probability=0.0,
        )
    )
    assert conn.execute("""
      SELECT COUNT(*) FROM changes_2026 e JOIN int_deferral_rate_state_accumulator s
      ON e.employee_id = s.employee_id AND s.simulation_year = 2025
      WHERE e.prev_employee_deferral_rate = s.current_deferral_rate
    """).fetchone()[0] == 100


@pytest.mark.parametrize(
    "reason", ["new", "inactive", "terminated", "dec31", "optout", "floor", "cap"]
)
def test_event_eligibility_and_noops(
    conn: duckdb.DuckDBPyConnection, reason: str
) -> None:
    fixture_inputs(conn)
    if reason == "new":
        conn.execute(
            "UPDATE int_baseline_workforce SET employee_enrollment_date = DATE '2025-01-01'"
        )
    elif reason == "inactive":
        conn.execute(
            "UPDATE int_employee_compensation_by_year SET employment_status = 'terminated'"
        )
    elif reason == "terminated":
        conn.execute(
            "UPDATE int_employee_termination_dates SET termination_date = DATE '2025-07-01'"
        )
    elif reason == "dec31":
        conn.execute(
            "UPDATE int_deferral_rate_escalation_events SET effective_date = DATE '2025-12-31'"
        )
    elif reason == "optout":
        conn.execute("""INSERT INTO int_enrollment_events
          SELECT employee_id, 'default', 2025, 'enrollment_change', DATE '2025-08-01', 0, '', 'enrollment_opt_out'
          FROM int_baseline_workforce""")
    elif reason in ("floor", "cap"):
        conn.execute("DELETE FROM int_deferral_match_response_events")
        conn.execute("DELETE FROM int_deferral_rate_escalation_events")
        conn.execute(
            "UPDATE int_baseline_workforce SET employee_deferral_rate = ?",
            [0.005 if reason == "floor" else 0.16],
        )
    variables = {}
    if reason in ("floor", "cap"):
        variables = {
            "deferral_rate_changes_with_escalation_increase_probability": int(
                reason == "cap"
            ),
            "deferral_rate_changes_with_escalation_decrease_probability": int(
                reason == "floor"
            ),
        }
    assert conn.execute(event_sql(**variables)).fetchall() == []


def test_probability_configuration_rejects_overlapping_mass() -> None:
    with pytest.raises(ValidationError, match="sum to at most 1"):
        DeferralRateChangesSettings(
            with_escalation={
                "increase_probability": 0.8,
                "decrease_probability": 0.3,
            }
        )
    with pytest.raises(ValidationError, match="weights/shares must sum to 1"):
        DeferralRateChangesSettings(increase_steps=[])


@pytest.mark.parametrize("mode", ["disabled", "census_optout", "participant_elected"])
def test_membership_selects_probability_group(
    conn: duckdb.DuckDBPyConnection, mode: str
) -> None:
    fixture_inputs(conn)
    variables: dict[str, Any] = {
        "deferral_rate_changes_without_escalation_increase_probability": 1.0,
        "deferral_rate_changes_without_escalation_decrease_probability": 0.0,
        "deferral_rate_changes_with_escalation_increase_probability": 0.0,
        "deferral_rate_changes_with_escalation_decrease_probability": 0.0,
    }
    if mode == "disabled":
        variables["deferral_escalation_enabled"] = False
    elif mode == "census_optout":
        conn.execute("UPDATE stg_census_data SET auto_escalation_opt_out = TRUE")
    else:
        variables["deferral_escalation_mode"] = "participant_elected"
        variables["deferral_escalation_participant_elected_signup_probability"] = 0.0
    rows = conn.execute(event_sql(**variables)).fetchall()
    assert len(rows) == 100 and {row[-1] for row in rows} == {"proactive_increase"}
    # Membership, not whether an escalation actually occurred, chooses the group.
    assert (
        conn.execute(
            event_sql(
                **(
                    variables
                    | {
                        "deferral_rate_changes_without_escalation_increase_probability": 0.0,
                    }
                )
            )
        ).fetchall()
        == []
    )


def test_prior_year_stopped_and_unenrolled_are_ineligible(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    fixture_inputs(conn)
    conn.execute("""
      CREATE TABLE int_deferral_rate_state_accumulator AS
      SELECT employee_id, 'default' AS scenario_id, 2025 AS simulation_year,
        CASE WHEN employee_id = 'employee-0' THEN .06 ELSE 0 END AS current_deferral_rate,
        employee_id <> 'employee-0' AS is_enrolled_flag, TRUE AS aip_participant,
        .06::DECIMAL(5,4) AS last_nonzero_deferral_rate
      FROM int_baseline_workforce;
      UPDATE int_employee_compensation_by_year SET simulation_year = 2026;
      UPDATE int_plan_design_assignment_accumulator SET simulation_year = 2026
    """)
    conn.execute(
        "CREATE TABLE fct_yearly_events AS SELECT *, 'default' AS scenario_id "
        "FROM (" + event_sql() + ") WHERE FALSE"
    )
    assert conn.execute(event_sql(2026)).fetchall() == []


def test_termination_window_and_timing_distribution(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    fixture_inputs(conn)
    conn.execute(
        "UPDATE int_employee_termination_dates SET termination_date = DATE '2025-07-31'"
    )
    rows = conn.execute(event_sql()).fetchall()
    dates = [row[4] for row in rows]
    assert len(rows) == 100
    assert min(dates).isoformat() >= "2025-07-02"
    assert max(dates).isoformat() <= "2025-07-31"
    assert len(set(dates)) >= 25


def test_prechange_double_roundoff_is_canonical_only_when_enabled(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    sql = """SELECT {{ rate_before_voluntary_change('FALSE', 'TRUE', '0.03',
      '0.06::DOUBLE + 0.01::DOUBLE', 'NULL', '0.01', '0.10', '50000', '40') }} AS rate
      FROM (SELECT 23500 base_limit, 31000 catch_up_limit, 50 catch_up_age_threshold,
        34750 super_catch_up_limit, 60 super_catch_up_age_min, 63 super_catch_up_age_max) il"""
    off = conn.execute(render(sql, deferral_rate_changes_enabled=False)).fetchone()[0]
    on = conn.execute(render(sql, deferral_rate_changes_enabled=True)).fetchone()[0]
    assert off == 0.06 + 0.01 and off != 0.07
    assert float(on) == 0.07


def sweep_rate_inputs(
    conn: duckdb.DuckDBPyConnection, year: int, escalation_date: str, match_date: str
) -> None:
    fixture_inputs(conn)
    conn.execute(
        "CREATE TABLE fct_yearly_events AS SELECT *, 'default' AS scenario_id, "
        "'default' AS plan_design_id, employee_id AS event_id FROM ("
        + event_sql()
        + ") WHERE FALSE"
    )
    if year == 2026:
        conn.execute(
            "CREATE TABLE int_deferral_rate_state_accumulator AS "
            + render(
                (DBT / STATE_MODEL).read_text(),
                simulation_year=2025,
                deferral_rate_changes_enabled=True,
            )
        )
    for table in (
        "int_employee_compensation_by_year",
        "int_plan_design_assignment_accumulator",
        "int_employee_termination_dates",
        "int_deferral_rate_escalation_events",
        "int_deferral_match_response_events",
    ):
        conn.execute(f"UPDATE {table} SET simulation_year = ?", [year])
    for table, date in (
        ("int_deferral_rate_escalation_events", escalation_date),
        ("int_deferral_match_response_events", match_date),
    ):
        conn.execute(f"UPDATE {table} SET effective_date = ?::DATE", [f"{year}-{date}"])
    conn.execute(
        """INSERT INTO int_enrollment_events SELECT employee_id, 'default', ?, 'enrollment',
      ?::DATE, .02, 'Re-enrollment sweep - 2% default deferral', 'auto_enrollment' FROM int_baseline_workforce""",
        [year, f"{year}-01-15"],
    )


def publish_sweep_changes(conn: duckdb.DuckDBPyConnection, year: int) -> None:
    conn.execute(
        "CREATE TABLE changes AS "
        + event_sql(
            year,
            deferral_rate_changes_with_escalation_increase_probability=1.0,
            deferral_rate_changes_with_escalation_decrease_probability=0.0,
        )
    )
    conn.execute(
        """INSERT INTO fct_yearly_events BY NAME SELECT *, 'default' AS scenario_id,
      'default' AS plan_design_id, employee_id || '-change' AS event_id FROM changes;
      INSERT INTO fct_yearly_events BY NAME SELECT * FROM int_enrollment_events;
      INSERT INTO fct_yearly_events BY NAME SELECT * FROM int_reenrollment_sweep_events;
      INSERT INTO fct_yearly_events BY NAME SELECT employee_id, simulation_year, effective_date,
        'deferral_escalation' AS event_type, new_deferral_rate AS employee_deferral_rate,
        previous_deferral_rate AS prev_employee_deferral_rate FROM int_deferral_rate_escalation_events;
      INSERT INTO fct_yearly_events BY NAME SELECT employee_id, simulation_year, effective_date,
        'deferral_match_response' AS event_type, employee_deferral_rate, prev_employee_deferral_rate
        FROM int_deferral_match_response_events;
    """
    )
    conn.execute(
        "CREATE TABLE resulting_state AS "
        + render(
            (DBT / STATE_MODEL).read_text(),
            simulation_year=year,
            deferral_rate_changes_enabled=True,
        )
    )


@pytest.mark.parametrize("year", [2025, 2026])
@pytest.mark.parametrize(
    "escalation_date,match_date,expected",
    [
        ("01-01", "01-01", 0.02),
        ("01-15", "01-15", 0.02),
        ("02-01", "02-01", 0.09),
        ("01-01", "02-01", 0.08),
        ("02-01", "01-01", 0.07),
    ],
)
def test_proactive_change_after_sweep_matches_accumulator(
    conn: duckdb.DuckDBPyConnection,
    year: int,
    escalation_date: str,
    match_date: str,
    expected: float,
) -> None:
    sweep_rate_inputs(conn, year, escalation_date, match_date)
    publish_sweep_changes(conn, year)
    rows = conn.execute(
        """SELECT COUNT(*), MIN(e.prev_employee_deferral_rate),
      MIN(s.rate_before_voluntary_change), MIN(s.current_deferral_rate),
      BOOL_AND(e.effective_date > GREATEST(?::DATE, ?::DATE))
      FROM changes e JOIN resulting_state s USING (employee_id)""",
        [f"{year}-{max(escalation_date, match_date)}", f"{year}-01-15"],
    ).fetchone()
    assert rows is not None and rows[0] == 100 and rows[4]
    assert float(rows[1]) == float(rows[2]) == expected
    assert float(rows[3]) == pytest.approx(expected + 0.02)


@pytest.mark.parametrize(
    "escalation,match,termination,days,lower,upper",
    [
        ("2025-01-01", "2025-01-01", None, 90, "2025-01-02", "2025-04-01"),
        ("2025-07-01", "2025-07-10", None, 90, "2025-07-11", "2025-09-29"),
        ("2025-12-01", "2025-01-01", None, 90, "2025-12-02", "2025-12-31"),
        ("2025-07-01", "2025-01-01", "2025-07-15", 90, "2025-07-02", "2025-07-15"),
        ("2025-07-01", "2025-01-01", None, 1, "2025-07-02", "2025-07-02"),
        ("2025-07-01", "2025-07-02", None, 1, None, None),
        ("2025-07-01", "2025-09-29", None, 90, None, None),
        ("2025-07-01", "2025-01-01", None, 0, None, None),
        ("2025-12-31", "2025-01-01", None, 90, None, None),
        ("2025-07-01", "2025-01-01", "2025-07-01", 90, None, None),
        (None, "2025-01-01", None, 0, "2025-01-02", "2025-12-31"),
        ("2024-07-01", "2025-01-01", None, 0, "2025-01-02", "2025-12-31"),
    ],
)
def test_response_event_window(
    conn: duckdb.DuckDBPyConnection,
    escalation: str | None,
    match: str,
    termination: str | None,
    days: int,
    lower: str | None,
    upper: str | None,
) -> None:
    fixture_inputs(conn)
    if escalation:
        conn.execute(
            "UPDATE int_deferral_rate_escalation_events SET effective_date = ?::DATE, "
            "simulation_year = YEAR(?::DATE)",
            [escalation, escalation],
        )
    else:
        conn.execute("DELETE FROM int_deferral_rate_escalation_events")
    conn.execute(
        "UPDATE int_deferral_match_response_events SET effective_date = ?::DATE",
        [match],
    )
    conn.execute(
        "UPDATE int_employee_termination_dates SET termination_date = ?::DATE",
        [termination],
    )
    rows = conn.execute(
        event_sql(
            deferral_rate_changes_with_escalation_increase_probability=0.0,
            deferral_rate_changes_with_escalation_decrease_probability=1.0,
            deferral_rate_changes_post_escalation_decrease_window_days=days,
        )
    ).fetchall()
    if lower is None:
        assert rows == []
        return
    category = (
        "aip_response_decrease"
        if escalation and escalation.startswith("2025")
        else "proactive_decrease"
    )
    assert len(rows) == 100 and {row[-1] for row in rows} == {category}
    assert all(lower <= row[4].isoformat() <= upper for row in rows)
    if lower != upper:
        assert len({row[4] for row in rows}) > 10


@pytest.mark.parametrize("year", [2025, 2026])
def test_sweep_keeps_notice_but_replaces_rate(
    conn: duckdb.DuckDBPyConnection, year: int
) -> None:
    sweep_rate_inputs(conn, year, "01-01", "01-01")
    rows = conn.execute(
        event_sql(
            year,
            deferral_rate_changes_with_escalation_increase_probability=0.0,
            deferral_rate_changes_with_escalation_decrease_probability=1.0,
        )
    ).fetchall()
    assert len(rows) == 100
    assert {row[-1] for row in rows} == {"aip_response_decrease"}
    assert all(float(row[9]) == 0.02 and float(row[8]) == 0.01 for row in rows)
    assert all(f"{year}-01-16" <= row[4].isoformat() <= f"{year}-04-01" for row in rows)


def response_state_fixture(conn: duckdb.DuckDBPyConnection) -> None:
    fixture_inputs(conn)
    conn.execute(
        "CREATE TABLE fct_yearly_events AS "
        "SELECT *, 'default' AS scenario_id, 'default' AS plan_design_id, "
        "employee_id || '-change' AS event_id FROM ("
        + event_sql(
            deferral_rate_changes_with_escalation_increase_probability=0.0,
            deferral_rate_changes_with_escalation_decrease_probability=1.0,
        )
        + ")"
    )
    # Published facts use TIMESTAMP even though the event model emits DATE.
    conn.execute(
        "ALTER TABLE fct_yearly_events ALTER COLUMN effective_date TYPE TIMESTAMP"
    )
    conn.execute(
        """INSERT INTO fct_yearly_events BY NAME
      SELECT employee_id, simulation_year, effective_date, 'deferral_escalation' AS event_type,
        'default' AS scenario_id, 'default' AS plan_design_id,
        new_deferral_rate AS employee_deferral_rate FROM int_deferral_rate_escalation_events"""
    )
    conn.execute(
        "CREATE TABLE int_deferral_rate_state_accumulator AS "
        + render(
            (DBT / STATE_MODEL).read_text(),
            simulation_year=2025,
            deferral_rate_changes_enabled=True,
        )
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "prior_year",
        "other_scenario",
        "same_day",
        "too_late",
        "terminated",
        "later_match",
        "wrong_rate",
        "wrong_category",
        "duplicate",
        "null_date",
    ],
)
def test_singular_response_guard_rejects_invalid_events(
    conn: duckdb.DuckDBPyConnection, mutation: str
) -> None:
    response_state_fixture(conn)
    sql = render(
        (DBT / "tests/assert_deferral_change_previous_rate.sql").read_text(),
        simulation_year=2025,
    )
    assert conn.execute(sql).fetchall() == []
    mutations = {
        "missing": "DELETE FROM fct_yearly_events WHERE event_type = 'deferral_escalation'",
        "prior_year": "UPDATE fct_yearly_events SET simulation_year = 2024 WHERE event_type = 'deferral_escalation'",
        "other_scenario": "UPDATE fct_yearly_events SET scenario_id = 'other' WHERE event_type = 'deferral_escalation'",
        "same_day": "UPDATE fct_yearly_events SET effective_date = DATE '2025-07-01' WHERE event_type = 'deferral_change'",
        "too_late": "UPDATE fct_yearly_events SET effective_date = DATE '2025-09-30' WHERE event_type = 'deferral_change'",
        "terminated": "UPDATE int_employee_termination_dates SET termination_date = DATE '2025-07-01'",
        "later_match": "INSERT INTO fct_yearly_events BY NAME SELECT employee_id, simulation_year, scenario_id, 'deferral_match_response' AS event_type, effective_date FROM fct_yearly_events WHERE event_type = 'deferral_change'",
        "wrong_rate": "UPDATE fct_yearly_events SET prev_employee_deferral_rate = .01 WHERE event_type = 'deferral_change'",
        "wrong_category": "UPDATE fct_yearly_events SET event_category = 'proactive_decrease' WHERE event_type = 'deferral_change'",
        "duplicate": "INSERT INTO fct_yearly_events SELECT * FROM fct_yearly_events WHERE event_type = 'deferral_change'",
        "null_date": "UPDATE fct_yearly_events SET effective_date = NULL WHERE event_type = 'deferral_change'",
    }
    conn.execute(mutations[mutation])
    assert len(conn.execute(sql).fetchall()) == (
        200 if mutation == "duplicate" else 100
    )


def test_response_settings_leave_increases_and_disabled_events_unchanged(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    fixture_inputs(conn)
    variables = {
        "deferral_rate_changes_with_escalation_increase_probability": 1.0,
        "deferral_rate_changes_with_escalation_decrease_probability": 0.0,
    }
    baseline = conn.execute(event_sql(**variables)).fetchall()
    assert len(baseline) == 100
    assert (
        conn.execute(
            event_sql(
                **variables,
                deferral_rate_changes_post_escalation_decrease_window_days=0,
                deferral_rate_changes_post_escalation_decrease_leaves_escalation=True,
            )
        ).fetchall()
        == baseline
    )
    assert (
        conn.execute(
            event_sql(
                deferral_rate_changes_enabled=False,
                deferral_rate_changes_post_escalation_decrease_leaves_escalation=True,
            )
        ).fetchall()
        == []
    )


def test_nonmember_without_escalation_decreases_proactively(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    fixture_inputs(conn)
    conn.execute("DELETE FROM int_deferral_rate_escalation_events")
    conn.execute("UPDATE stg_census_data SET auto_escalation_opt_out = TRUE")
    rows = conn.execute(
        event_sql(
            deferral_rate_changes_without_escalation_increase_probability=0.0,
            deferral_rate_changes_without_escalation_decrease_probability=1.0,
            deferral_rate_changes_post_escalation_decrease_window_days=0,
        )
    ).fetchall()
    assert len(rows) == 100 and {row[-1] for row in rows} == {"proactive_decrease"}


@pytest.mark.parametrize("year", [2025, 2026])
def test_contributor_sweep_precedes_separate_voluntary_change(
    conn: duckdb.DuckDBPyConnection, year: int
) -> None:
    sweep_rate_inputs(conn, year, "01-01", "01-01")
    conn.execute("""INSERT INTO int_reenrollment_sweep_events
      SELECT employee_id, scenario_id, simulation_year, 'deferral_change', effective_date,
        .09, 'Re-enrollment sweep - 9% deferral; method=enroll_at_default', 'reenrollment_sweep'
      FROM int_enrollment_events;
      DELETE FROM int_enrollment_events;
    """)
    publish_sweep_changes(conn, year)
    row = conn.execute("""SELECT COUNT(*), MIN(c.prev_employee_deferral_rate),
      MIN(s.current_deferral_rate), BOOL_AND(c.effective_date > DATE '2025-01-15'),
      BOOL_AND(s.aip_participant)
      FROM changes c JOIN resulting_state s USING (employee_id)""").fetchone()
    assert row is not None and row[0] == 100
    assert float(row[1]) == 0.09 and float(row[2]) == 0.11
    assert row[3] and row[4]
    assert (
        conn.execute("""SELECT MAX(n) FROM (SELECT employee_id, COUNT(*) n
      FROM fct_yearly_events WHERE event_type = 'deferral_change'
      AND event_category <> 'reenrollment_sweep' GROUP BY employee_id)""").fetchone()[0]
        == 1
    )


@pytest.mark.parametrize("accepted", [True, False])
def test_contributor_sweep_elects_aip_only_when_accepted(
    conn: duckdb.DuckDBPyConnection, accepted: bool
) -> None:
    sweep_rate_inputs(conn, 2025, "01-01", "01-01")
    conn.execute("DELETE FROM int_enrollment_events")
    conn.execute("UPDATE stg_census_data SET auto_escalation_opt_out = TRUE")
    if accepted:
        conn.execute("""INSERT INTO fct_yearly_events BY NAME
          SELECT employee_id, 'default' AS scenario_id, 'default' AS plan_design_id,
            2025 AS simulation_year, DATE '2025-01-15' AS effective_date,
            'deferral_change' AS event_type, 'reenrollment_sweep' AS event_category,
            'Re-enrollment sweep - 6% deferral; method=into_aip' AS event_details,
            .06 AS employee_deferral_rate FROM int_baseline_workforce""")
    state = conn.execute(
        render((DBT / STATE_MODEL).read_text(), simulation_year=2025)
    ).fetchdf()
    assert set(state.aip_participant) == {accepted}
    assert set(state.current_deferral_rate) == {0.06 if accepted else 0.09}


@pytest.mark.parametrize("direction", ["increase", "decrease"])
@pytest.mark.parametrize("dimension", ["age", "income", "tenure"])
def test_multiplier_lower_bounds(
    conn: duckdb.DuckDBPyConnection, direction: str, dimension: str
) -> None:
    bands = [
        {"min": 0, "multiplier": 1.0},
        {"min": 30, "multiplier": 0.0},
        {"min": 70, "multiplier": 2.0},
    ]
    variable = f"deferral_rate_changes_multipliers_{direction}_{dimension}"
    sql = "SELECT {{ deferral_change_multiplier('v', var('" + variable + "')) }} "
    sql += "FROM (VALUES (NULL), (-1), (0), (29.999), (30), (69.999), (70), (1000000)) t(v)"
    assert [
        row[0] for row in conn.execute(render(sql, **{variable: bands})).fetchall()
    ] == [1, 1, 1, 1, 0, 0, 2, 2]


def test_probability_product(conn: duckdb.DuckDBPyConnection) -> None:
    sql = "SELECT {{ deferral_change_probability_product('0.2', 'increase', '40', '125000', '10') }}"
    variables = {
        f"deferral_rate_changes_multipliers_increase_{dimension}": [
            {"min": 0, "multiplier": 1},
            {"min": bound, "multiplier": factor},
        ]
        for dimension, bound, factor in [
            ("age", 40, 2),
            ("income", 125000, 3),
            ("tenure", 10, 0.5),
        ]
    }
    assert conn.execute(render(sql, **variables)).fetchone()[0] == pytest.approx(0.6)


@pytest.mark.parametrize(
    "increase,decrease,stop,expected",
    [
        (0.2, 0.3, 0.1, (0.2, 0.3)),
        (2.0, 1.0, 0.1, (0.6, 0.3)),
        (0.0, 0.0, 1.0, (0.0, 0.0)),
        (1.0, 0.0, 1.0, (0.0, 0.0)),
        (0.0, 3.0, 0.2, (0.0, 0.8)),
        (0.4, 0.5, 0.1, (0.4, 0.5)),
    ],
)
def test_proportional_probability_rescale(
    conn: duckdb.DuckDBPyConnection,
    increase: float,
    decrease: float,
    stop: float,
    expected: tuple[float, float],
) -> None:
    sql = """SELECT
      {{ deferral_change_rescaled_probability('i', 'd', 's') }},
      {{ deferral_change_rescaled_probability('d', 'i', 's') }}
      FROM (VALUES ({{ var('i') }}, {{ var('d') }}, {{ var('s') }})) t(i, d, s)"""
    actual = conn.execute(render(sql, i=increase, d=decrease, s=stop)).fetchone()
    assert tuple(map(float, actual)) == pytest.approx(expected)
    assert sum(map(float, actual)) + stop <= 1


@pytest.mark.parametrize(
    "increase,decrease,stop", [(0.2, 0.3, 0.1), (2.0, 1.0, 0.1), (0.0, 0.0, 1.0)]
)
def test_rendered_model_uses_multiplied_probabilities(
    conn: duckdb.DuckDBPyConnection,
    increase: float,
    decrease: float,
    stop: float,
) -> None:
    fixture_inputs(conn)
    # Inputs are age 40, annual compensation 50,000 and tenure 5: exercise all boundaries.
    variables = {"deferral_rate_changes_stop_probability": stop}
    for direction, raw in [("increase", increase), ("decrease", decrease)]:
        for dimension, bound, factor in [
            ("age", 40, 2),
            ("income", 50000, 3),
            ("tenure", 5, raw / 3),
        ]:
            variables[f"deferral_rate_changes_multipliers_{direction}_{dimension}"] = [
                {"min": 0, "multiplier": 0},
                {"min": bound, "multiplier": factor},
            ]
    sql = event_sql(**variables)
    # The CTE output checks probabilities even for participants drawing no event.
    prefix = sql[: sql.rindex("\nSELECT\n  employee_id::VARCHAR")]
    probabilities = conn.execute(
        prefix + " SELECT increase_probability, decrease_probability FROM probabilities"
    ).fetchall()
    scale = min(1, (1 - stop) / (increase + decrease)) if increase + decrease else 1
    assert all(
        tuple(map(float, row)) == pytest.approx((increase * scale, decrease * scale))
        for row in probabilities
    )
    assert all(sum(map(float, row)) + stop <= 1 for row in probabilities)
    rows = conn.execute(sql).fetchall()
    expected = {
        "proactive_increase": increase * scale,
        "aip_response_decrease": decrease * scale,
        "stop": stop,
    }
    assert rows
    assert all(
        float(row[-2]) == pytest.approx(expected[row[-1]], abs=0.00005) for row in rows
    )


@pytest.mark.parametrize("direction", ["increase", "decrease"])
def test_dbt_step_fallback_matches_fitted_defaults(
    conn: duckdb.DuckDBPyConnection, direction: str
) -> None:
    steps = getattr(DeferralRateChangesSettings(), f"{direction}_steps")
    cumulative = 0.0
    for step in steps:
        midpoint = cumulative + step.weight / 2
        sql = (
            "SELECT {{ deferral_change_step('"
            + str(midpoint)
            + "', '"
            + direction
            + "') }}"
        )
        assert conn.execute(render(sql)).fetchone()[0] == step.pp
        cumulative += step.weight


@pytest.mark.parametrize("direction", ["increase", "decrease"])
@pytest.mark.parametrize("dimension", ["age", "income", "tenure"])
def test_dbt_multiplier_fallback_matches_fitted_defaults(
    conn: duckdb.DuckDBPyConnection, direction: str, dimension: str
) -> None:
    defaults = getattr(DeferralRateChangesSettings().multipliers, direction)
    bands = getattr(defaults, dimension)
    variables = {
        f"deferral_rate_changes_multipliers_{direction}_{other}": [
            {"min": 0, "multiplier": 1.0}
        ]
        for other in ("age", "income", "tenure")
        if other != dimension
    }
    inputs = [
        "v" if other == dimension else "0" for other in ("age", "income", "tenure")
    ]
    macro = "{{ deferral_change_probability_product('1', '" + direction + "', "
    macro += ", ".join(repr(value) for value in inputs) + ") }}"
    values = [
        -1,
        0,
        *[band.min + offset for band in bands for offset in (-0.001, 0)],
        1e9,
    ]
    sql = f"SELECT v, {macro} FROM (VALUES "
    sql += ", ".join(f"({value})" for value in values) + ") t(v)"
    for value, multiplier in conn.execute(render(sql, **variables)).fetchall():
        expected = next(
            (band.multiplier for band in reversed(bands) if value >= band.min),
            bands[0].multiplier,
        )
        assert multiplier == pytest.approx(expected)
