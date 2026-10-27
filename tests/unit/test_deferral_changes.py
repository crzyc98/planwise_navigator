"""Execute proactive change macros and the real event/accumulator SQL in DuckDB."""

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
    "utils/subsystem_seed.sql",
    "utils/stable_decimal.sql",
    "constants.sql",
    "self_directed_enrollment_rate.sql",
    "aip_initial_membership.sql",
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


def test_probability_boundaries(conn: duckdb.DuckDBPyConnection) -> None:
    rows = conn.execute(render("""
      SELECT u, {{ deferral_change_category('u', '0.25', '0.075') }}
      FROM (VALUES (0.0), (0.249999), (0.25), (0.324999), (0.325), (0.999999)) t(u)
      ORDER BY u
    """)).fetchall()
    assert [row[1] for row in rows] == [
        "proactive_increase",
        "proactive_increase",
        "proactive_decrease",
        "proactive_decrease",
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
        FROM range(20000) r(i)
      )
      SELECT {{ deferral_change_category('u', '0.25', '0.075') }} AS category,
        {{ deferral_change_step('s', 'increase') }} AS step, COUNT(*), AVG(t)
      FROM draws GROUP BY ALL ORDER BY ALL
    """
    rows = conn.execute(render(sql)).fetchall()
    assert rows == conn.execute(render(sql)).fetchall()
    assert (
        rows != conn.execute(render(sql, random_seed_deferral_behavior=43)).fetchall()
    )
    for category, expected in [
        ("proactive_increase", 0.25),
        ("proactive_decrease", 0.075),
    ]:
        total = sum(n for c, _, n, _ in rows if c == category)
        assert total / 20000 == pytest.approx(expected, abs=0.01)
        for step, weight in [
            (1, 0.15),
            (2, 0.20),
            (3, 0.15),
            (5, 0.20),
            (7, 0.15),
            (10, 0.15),
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
        .06::DECIMAL(5,4) AS employee_deferral_rate, '' AS event_details
      FROM int_baseline_workforce WHERE FALSE;
    """)


def event_sql(year: int = 2025, **variables: Any) -> str:
    defaults = {
        "simulation_year": year,
        "deferral_rate_changes_enabled": True,
        "deferral_rate_changes_with_escalation_increase_probability": 0.5,
        "deferral_rate_changes_with_escalation_decrease_probability": 0.5,
        "deferral_rate_changes_increase_steps": [{"pp": 2, "weight": 1}],
        "deferral_rate_changes_decrease_steps": [{"pp": 2, "weight": 1}],
    }
    return render((DBT / EVENT_MODEL).read_text(), **(defaults | variables))


def test_real_accumulator_two_year_carry_and_escalation(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """#983 acceptance: real generated changes -> real state -> next-year state."""
    fixture_inputs(conn)
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
    conn.execute(
        "CREATE TABLE int_deferral_rate_state_accumulator AS "
        + render(
            (DBT / STATE_MODEL).read_text(),
            simulation_year=2025,
            deferral_rate_changes_enabled=True,
        )
    )
    rows = conn.execute("""
      SELECT e.event_category, COUNT(*), MIN(s.rate_before_voluntary_change),
        MIN(s.current_deferral_rate), MIN(s.last_nonzero_deferral_rate),
        BOOL_AND(e.effective_date > DATE '2025-07-01')
      FROM changes e JOIN int_deferral_rate_state_accumulator s USING (employee_id)
      GROUP BY 1 ORDER BY 1
    """).fetchall()
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
            deferral_rate_changes_enabled=True,
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
    # Generator must also start from carried state, not original census rates.
    conn.execute("CREATE TABLE changes_2026 AS " + event_sql(2026))
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
          SELECT employee_id, 'default', 2025, 'enrollment_change', DATE '2025-08-01', 0, ''
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
        employee_id <> 'employee-0' AS is_enrolled_flag, TRUE AS aip_participant
      FROM int_baseline_workforce;
      UPDATE int_employee_compensation_by_year SET simulation_year = 2026;
      UPDATE int_plan_design_assignment_accumulator SET simulation_year = 2026
    """)
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
    off = conn.execute(render(sql)).fetchone()[0]
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
      ?::DATE, .02, 'Re-enrollment sweep - 2% default deferral' FROM int_baseline_workforce""",
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
