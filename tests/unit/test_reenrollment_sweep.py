"""Execute production candidate selection and sweep schedules in DuckDB."""

from pathlib import Path
from typing import Any

import duckdb
from jinja2 import Environment, StrictUndefined
import pytest
from pydantic import ValidationError

from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.config.dbt_var_validation import validate_dbt_vars
from planalign_orchestrator.config.export import to_dbt_vars
from planalign_orchestrator.config.workforce import ReenrollmentSweepSettings

pytestmark = pytest.mark.fast
DBT = Path(__file__).resolve().parents[2] / "dbt"


def render(source: str, **variables: Any) -> str:
    macros = "\n".join(
        (DBT / "macros" / name).read_text()
        for name in ("enrollment_eligibility.sql", "reenrollment_sweep.sql")
    )
    return (
        Environment(undefined=StrictUndefined)
        .from_string(macros + source)
        .render(
            var=lambda name, default=None: variables.get(name, default),
            **{"return": lambda value: value},
        )
    )


@pytest.mark.parametrize(
    "interval,first,years",
    [
        (3, None, [2028, 2031]),
        (1, None, list(range(2026, 2033))),
        (2, 2027, [2027, 2029, 2031]),
        (2, 2023, [2025, 2027, 2029, 2031]),
    ],
)
def test_sweep_schedule(interval: int, first: int | None, years: list[int]) -> None:
    sql = render(
        "SELECT year FROM range(2025, 2033) t(year) WHERE "
        f"{{{{ is_reenrollment_sweep_year('year', 'TRUE', '{interval}', '{first if first is not None else 'NULL'}') }}}}"
    )
    with duckdb.connect() as conn:
        assert [row[0] for row in conn.execute(sql).fetchall()] == years


@pytest.mark.parametrize(
    "field,value",
    [
        ("interval_years", 0),
        ("interval_years", -1),
        ("interval_years", 1.5),
        ("interval_years", True),
        ("first_year", 2027.5),
        ("first_year", True),
    ],
)
def test_config_rejects_invalid_sweep_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        ReenrollmentSweepSettings.model_validate({field: value})
    assert validate_dbt_vars({f"reenrollment_sweep_{field}": value})


def test_default_and_yaml_export() -> None:
    config = load_simulation_config("config/simulation_config.yaml")
    assert (
        config.enrollment.auto_enrollment.reenrollment_sweep
        == ReenrollmentSweepSettings()
    )
    config.enrollment.auto_enrollment.reenrollment_sweep = ReenrollmentSweepSettings(
        enabled=True, interval_years=2, first_year=2027
    )
    variables = to_dbt_vars(config)
    assert {
        key: value
        for key, value in variables.items()
        if key.startswith("reenrollment_sweep_")
    } == {
        "reenrollment_sweep_enabled": True,
        "reenrollment_sweep_interval_years": 2,
        "reenrollment_sweep_first_year": 2027,
    }
    assert not validate_dbt_vars(variables)


def candidate_sql(year: int) -> str:
    source = (DBT / "models/intermediate/int_enrollment_events.sql").read_text()
    # Execute the actual candidate-selection CTE, supplying its two input relations.
    start = source.index("auto_enrollment_eligible_population AS (")
    end = source.index("eligible_for_enrollment AS (", start)
    cte = source[start:end].rstrip().removesuffix(",")
    return render(
        "WITH "
        + cte
        + " SELECT employee_id FROM auto_enrollment_eligible_population WHERE is_auto_enrollment_eligible ORDER BY employee_id",
        simulation_year=year,
        start_year=2025,
    )


@pytest.mark.parametrize("scope", ["new_hires_only", "all_eligible_employees"])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("year", [2026, 2027, 2028, 2029])
def test_candidates(scope: str, enabled: bool, year: int) -> None:
    with duckdb.connect() as conn:
        conn.execute(
            """CREATE TABLE active_workforce AS
          SELECT employee_id, DATE '2021-01-01' AS employee_hire_date,
            ?::INTEGER AS simulation_year, 'active' AS employment_status,
            ?::VARCHAR AS auto_enrollment_scope, TRUE AS is_plan_eligible,
            FALSE AS is_plan_ineligible_override, DATE '2021-02-01' AS plan_eligibility_date,
            45 AS auto_enrollment_window_days,
            ?::BOOLEAN AS reenrollment_sweep_enabled, 2 AS reenrollment_sweep_interval_years,
            2027 AS reenrollment_sweep_first_year
          FROM (VALUES ('optout'), ('zero'), ('never'), ('contributor'), ('ineligible'), ('cutoff'), ('inactive'), ('late')) t(employee_id)""",
            [year, scope, enabled],
        )
        conn.execute(
            """CREATE TABLE previous_enrollment_state AS
          SELECT employee_id, employee_id IN ('zero', 'contributor') AS was_enrolled_previously,
            employee_id IN ('optout', 'zero') AS ever_opted_out,
            CASE WHEN employee_id = 'contributor' THEN 0.06 ELSE 0 END AS current_deferral_rate,
            current_deferral_rate AS sweep_deferral_rate, NULL::DATE AS latest_opt_out_date
          FROM active_workforce;
          UPDATE active_workforce SET is_plan_eligible = FALSE WHERE employee_id = 'ineligible';
          UPDATE active_workforce SET employee_hire_date = DATE '2019-01-01' WHERE employee_id = 'cutoff';
          UPDATE active_workforce SET employment_status = 'terminated' WHERE employee_id = 'inactive';
          UPDATE active_workforce SET is_plan_eligible = FALSE, plan_eligibility_date = DATE '2035-01-01' WHERE employee_id = 'late';"""
        )
        ids = {row[0] for row in conn.execute(candidate_sql(year)).fetchall()}
        sweep_year = enabled and year in (2027, 2029)
        expected = (
            {"optout", "zero", "never"}
            if sweep_year
            else ({"never"} if scope == "all_eligible_employees" else set())
        )
        assert ids == expected
        # The periodic sweep itself is inactive between sweep years, even when
        # ordinary all-eligible AE can still select a never-enrolled employee.
        sweep_ids = conn.execute(
            render(
                "SELECT aw.employee_id FROM active_workforce aw LEFT JOIN previous_enrollment_state pe USING (employee_id) WHERE {{ is_reenrollment_sweep_candidate('aw', 'pe') }}"
            )
        ).fetchall()
        assert {row[0] for row in sweep_ids} == (
            {"optout", "zero", "never"} if sweep_year else set()
        )


def test_per_design_sweep_schedule_and_defaults() -> None:
    from planalign_orchestrator.config.plan_design import AutoEnrollmentParameterSet

    terms = AutoEnrollmentParameterSet(
        default_deferral_rate=0.07,
        window_days=30,
        scope="new_hires_only",
        reenrollment_sweep={"enabled": True, "interval_years": 2, "first_year": 2027},
    )
    assert terms.reenrollment_sweep.first_year == 2027
    with pytest.raises(ValidationError):
        AutoEnrollmentParameterSet(
            default_deferral_rate=0.07,
            window_days=30,
            scope="new_hires_only",
            reenrollment_sweep={"interval_years": 0},
        )
    source = (DBT / "macros/get_plan_design_parameters.sql").read_text()
    from tests.unit.test_easy_enroll import _plan_parameters

    active = _plan_parameters(0.01)
    active["auto_enrollment"][
        "reenrollment_sweep"
    ] = terms.reenrollment_sweep.model_dump()
    sql = render(
        source
        + "WITH parameters AS ({{ get_plan_design_parameters(var('plan_design_parameters')) }}) SELECT plan_design_id FROM parameters WHERE {{ is_reenrollment_sweep_year('2027', 'reenrollment_sweep_enabled', 'reenrollment_sweep_interval_years', 'reenrollment_sweep_first_year') }}",
        plan_design_parameters={"on": active, "off": _plan_parameters(0.01)},
    )
    with duckdb.connect() as conn:
        assert conn.execute(sql).fetchall() == [("on",)]


def render_events(source: str, **variables: Any) -> str:
    macros = "\n".join(
        (DBT / "macros" / name).read_text()
        for name in ("utils/subsystem_seed.sql", "self_directed_enrollment_rate.sql")
    )
    return (
        Environment(undefined=StrictUndefined)
        .from_string(
            "\n".join(
                (DBT / "macros" / name).read_text()
                for name in ("enrollment_eligibility.sql", "reenrollment_sweep.sql")
            )
            + macros
            + source
        )
        .render(
            var=lambda name, default=None: variables.get(name, default),
            ref=lambda name: name,
            config=lambda **kwargs: "",
            target={"schema": "main"},
            is_incremental=lambda: False,
            **{"return": lambda value: value},
        )
    )


@pytest.mark.parametrize("opt_out_rate", [0.0, 1.0])
def test_sweep_election_and_repeat_optout_survive_final_deduplication(
    opt_out_rate: float,
) -> None:
    source = (DBT / "models/intermediate/int_enrollment_events.sql").read_text()
    candidates = source[
        source.index("eligible_for_enrollment AS (") : source.index(
            "-- Epic E053: Voluntary Enrollment Events Integration"
        )
    ]
    optouts = source[
        source.index("opt_out_candidates AS (") : source.index(
            "-- Combine all enrollment-related events"
        )
    ]
    # Keep real candidate, election, opt-out, deduplication and final projection SQL.
    tail = source[source.index("all_enrollment_events AS (") :]
    sql = render_events(
        "{% set flat_new_hire_opt_out_rate = none %}WITH "
        + candidates
        + optouts
        + tail,
        simulation_year=2027,
        start_year=2025,
        **{
            f"opt_out_rate_{age}": opt_out_rate
            for age in ("young", "mid", "mature", "senior")
        },
    )
    with duckdb.connect() as conn:
        stable = (
            Environment()
            .from_string((DBT / "macros/utils/stable_hash.sql").read_text())
            .module
        )
        conn.execute(getattr(stable, "install_stable_hash")())
        conn.execute("""CREATE TABLE active_workforce AS SELECT employee_id,
          'synthetic' AS employee_ssn, DATE '2021-01-01' AS employee_hire_date,
          2027 AS simulation_year, 'active' AS employment_status,
          'new_hires_only' AS auto_enrollment_scope, TRUE AS is_plan_eligible,
          FALSE AS is_plan_ineligible_override, DATE '2021-02-01' AS plan_eligibility_date,
          TRUE AS reenrollment_sweep_enabled, 2 AS reenrollment_sweep_interval_years,
          2027 AS reenrollment_sweep_first_year, 40 AS current_age, 6 AS current_tenure,
          75000 AS current_compensation, 1 AS level_id, '35-44' AS age_band,
          '5-9' AS tenure_band, 0.06 AS auto_enrollment_default_deferral_rate,
          45 AS auto_enrollment_window_days
          FROM (VALUES ('optout'), ('zero'), ('never')) t(employee_id);
          CREATE TABLE previous_enrollment_state AS SELECT employee_id,
            employee_id = 'zero' AS was_enrolled_previously,
            employee_id != 'never' AS ever_opted_out, 0 AS current_deferral_rate,
            0 AS sweep_deferral_rate, NULL::DATE AS latest_opt_out_date,
            DATE '2025-02-01' AS previous_enrollment_date, 'auto' AS enrollment_source,
            2 AS years_since_first_enrollment FROM active_workforce;
          CREATE TABLE int_employee_termination_dates AS SELECT employee_id,
            simulation_year, NULL::DATE AS termination_date FROM active_workforce;""")
        # Empty employee-initiated channels: those retain their existing priority.
        schema = render_events(
            "WITH "
            + candidates.rstrip().removesuffix(",")
            + " SELECT * FROM enrollment_events WHERE FALSE",
            simulation_year=2027,
        )
        for table in (
            "voluntary_enrollment_events",
            "proactive_voluntary_enrollment_events",
            "year_over_year_enrollment_events",
        ):
            conn.execute(f"CREATE TABLE {table} AS {schema}")
        result = conn.execute(sql).fetchdf()
        enrollments = result[result.event_type == "enrollment"]
        assert set(enrollments.employee_id) == {"optout", "zero", "never"}
        assert set(enrollments.event_category) == {"auto_enrollment"}
        assert set(enrollments.employee_deferral_rate) == {0.06}
        assert enrollments.event_details.str.startswith("Re-enrollment sweep - ").all()
        assert len(result[result.event_type == "enrollment_change"]) == int(
            3 * opt_out_rate
        )
        assert (
            conn.execute(sql)
            .fetchdf()
            .drop(columns="created_at")
            .equals(result.drop(columns="created_at"))
        )


@pytest.mark.parametrize(
    "enabled,year,violations",
    [
        (False, 2027, 1),
        (True, 2026, 1),
        (True, 2027, 0),
        (True, 2028, 1),
        (True, 2029, 0),
    ],
)
def test_post_optout_guard_checks_each_election_even_if_employee_opts_out_again(
    enabled: bool, year: int, violations: int
) -> None:
    source = (DBT / "tests/data_quality/test_enrollment_after_optout.sql").read_text()
    sql = render_events(
        source,
        simulation_year=year,
        reenrollment_sweep_enabled=enabled,
        reenrollment_sweep_interval_years=2,
        reenrollment_sweep_first_year=2027,
    )
    with duckdb.connect() as conn:
        conn.execute(
            """CREATE TABLE fct_yearly_events AS
          SELECT 'employee' AS employee_id, 'default' AS scenario_id,
            year AS simulation_year, MAKE_DATE(year, month, 15) AS effective_date,
            type AS event_type, category AS event_category, details AS event_details
          FROM (VALUES (2025, 6, 'enrollment_change', 'enrollment_opt_out', 'opt-out'),
            (?, 1, 'enrollment', 'auto_enrollment', 'Re-enrollment sweep - 6%'),
            (?, 6, 'enrollment_change', 'enrollment_opt_out', 'opt-out')) t(year,month,type,category,details)""",
            [year, year],
        )
        conn.execute(
            """CREATE TABLE int_plan_design_assignment_accumulator AS SELECT DISTINCT
            employee_id, scenario_id, simulation_year, 'default' AS plan_design_id
          FROM fct_yearly_events;"""
        )
        assert len(conn.execute(sql).fetchall()) == violations


def _accumulator_rate_sql(first_year: bool) -> str:
    source = (
        DBT / "models/intermediate/int_deferral_rate_state_accumulator.sql"
    ).read_text()
    branch = source[
        source.index(
            "first_year_state AS (" if first_year else "subsequent_year_state AS ("
        ) :
    ]
    # Rendered through the shared macro, exactly as the accumulator calls it.
    rate = branch[
        branch.index("{{ rate_before_voluntary_change(") : branch.index(
            "}} as rate_before_voluntary_change,"
        )
        + len("}}")
    ]
    joins = branch[
        branch.index("    FROM current_year_workforce w") : branch.index(
            "    CROSS JOIN irs_limits il"
        )
        + len("    CROSS JOIN irs_limits il")
    ]
    return (
        Environment(undefined=StrictUndefined)
        .from_string(
            (DBT / "macros/deferral_change.sql").read_text()
            + "SELECT "
            + rate
            + " AS rate "
            + joins
        )
        .render(
            ref=lambda name: name,
            simulation_year=2027,
            scenario_id="default",
            var=lambda name, default=None: default,
            irs_402g_limit_for_age=lambda *args: "23500",
        )
    )


def _accumulator_inputs(
    conn: duckdb.DuckDBPyConnection, sweep: bool, later: bool, optout: bool
) -> None:
    conn.execute(
        """CREATE TABLE current_year_workforce AS SELECT 'employee' AS employee_id,
      75000 AS employee_compensation, DATE '1987-01-01' AS employee_birth_date, 40 AS current_age;
      CREATE TABLE int_plan_design_assignment_accumulator AS SELECT 'employee' AS employee_id,
        'default' AS scenario_id, 'default' AS plan_design_id, 2027 AS simulation_year;
      CREATE TABLE previous_year_state AS SELECT 'employee' AS employee_id, 0.0 AS previous_deferral_rate;
      CREATE TABLE baseline_deferral_rates AS SELECT 'employee' AS employee_id, 0.06 AS fallback_rate;
      CREATE TABLE irs_limits AS SELECT 1 AS placeholder;
      CREATE TABLE current_year_match_response AS SELECT 'employee' AS employee_id,
        0.08 AS match_responsive_rate, 1 AS rn, DATE '2027-01-01' AS effective_date WHERE FALSE;"""
    )
    conn.execute(
        """CREATE TABLE current_year_new_enrollments AS SELECT 'employee' AS employee_id,
      ?::BOOLEAN AS is_reenrollment_sweep, 0.02 AS initial_deferral_rate,
      1 AS rn, DATE '2027-01-15' AS enrollment_date""",
        [sweep],
    )
    conn.execute(
        "CREATE TABLE first_year_enrolled_employees AS SELECT * FROM current_year_new_enrollments"
    )
    conn.execute(
        """CREATE TABLE current_year_escalations AS SELECT 'employee' AS employee_id,
      0.03 AS new_deferral_rate, 0.01 AS escalation_rate, 0.10 AS max_escalation_rate,
      1 AS rn, MAKE_DATE(2027, ?, 1) AS effective_date""",
        [2 if later else 1],
    )
    conn.execute(
        "CREATE TABLE current_year_opt_outs AS SELECT 'employee' AS employee_id WHERE ?",
        [optout],
    )


@pytest.mark.parametrize("first_year", [False, True])
@pytest.mark.parametrize(
    "sweep,later,optout,expected",
    [
        (True, False, False, 0.02),
        (True, True, False, 0.03),
        (True, False, True, 0.0),
        (False, False, False, 0.03),
    ],
)
def test_sweep_replaces_earlier_rate_decisions_in_both_accumulator_branches(
    first_year: bool, sweep: bool, later: bool, optout: bool, expected: float
) -> None:
    with duckdb.connect() as conn:
        _accumulator_inputs(conn, sweep, later, optout)
        rate = conn.execute(_accumulator_rate_sql(first_year)).fetchone()
        assert rate is not None
        assert float(rate[0]) == expected


def sweep_candidate_inputs(
    conn: duckdb.DuckDBPyConnection,
    year: int,
    optout_date: str,
    prior_rate: float,
    pending_date: str | None,
) -> None:
    conn.execute("""CREATE TABLE active_workforce AS SELECT 'late_hire' AS employee_id,
      DATE '2025-12-27' AS employee_hire_date, 2026 AS simulation_year,
      'active' AS employment_status, 'all_eligible_employees' AS auto_enrollment_scope,
      TRUE AS is_plan_eligible, FALSE AS is_plan_ineligible_override,
      DATE '2025-12-27' AS plan_eligibility_date, 45 AS auto_enrollment_window_days,
      TRUE AS reenrollment_sweep_enabled, 1 AS reenrollment_sweep_interval_years,
      NULL::INTEGER AS reenrollment_sweep_first_year;
      CREATE TABLE stg_prior_enrollment_state AS SELECT employee_id,
        DATE '2026-02-10' AS enrollment_date, FALSE AS is_enrolled, TRUE AS ever_opted_out,
        0 AS current_deferral_rate, 'fct_yearly_events' AS enrollment_source FROM active_workforce;
      CREATE TABLE fct_yearly_events (employee_id VARCHAR, scenario_id VARCHAR,
        simulation_year INTEGER, effective_date DATE, event_type VARCHAR,
        event_details VARCHAR, employee_deferral_rate DECIMAL(5,4), event_sequence INTEGER, event_id VARCHAR);
    """)
    conn.execute(
        """INSERT INTO fct_yearly_events VALUES
      ('late_hire', 'default', 2025, ?, 'enrollment_change', 'opt-out', 0, 2, 'optout'),
      ('late_hire', 'default', 2025, '2026-02-10', 'enrollment', 'Auto-enrollment', .02, 1, 'enroll')""",
        [optout_date],
    )
    conn.execute(
        """CREATE TABLE int_deferral_rate_state_accumulator AS
      SELECT employee_id, 'default' AS scenario_id, 2025 AS simulation_year,
        ?::DECIMAL(5,4) AS current_deferral_rate FROM active_workforce""",
        [prior_rate],
    )
    conn.execute("UPDATE active_workforce SET simulation_year = ?", [year])
    conn.execute(
        "UPDATE int_deferral_rate_state_accumulator SET simulation_year = ?",
        [year - 1],
    )
    if pending_date:
        conn.execute(
            "UPDATE fct_yearly_events SET effective_date = ? WHERE event_id = 'enroll'",
            [pending_date],
        )


@pytest.mark.parametrize(
    "year,optout_date,prior_rate,pending_date,expected",
    [
        (
            2026,
            "2026-03-12",
            0.0,
            None,
            False,
        ),  # Late-year hire: opt-out still pending.
        (2026, "2026-01-15", 0.0, None, False),  # Equal dates are not after opt-out.
        (2026, "2026-01-14", 0.0, None, True),
        (2026, "2025-06-15", 0.02, None, False),  # Stale unenrolled projection.
        (
            2026,
            "2025-06-15",
            0.0,
            "2026-01-10",
            False,
        ),  # Pending enrollment now effective.
        (2026, "2026-01-14", 0.02, None, True),  # Pending opt-out now effective.
        (2026, "2027-03-12", 0.0, None, False),
        (2027, "2026-03-12", 0.0, None, True),  # Prior opt-out has now taken effect.
        (
            2027,
            "2026-03-12",
            0.02,
            None,
            False,
        ),  # Positive state always blocks a repeat sweep.
    ],
)
def test_sweep_uses_effective_optout_and_deferral_state(
    year: int,
    optout_date: str,
    prior_rate: float,
    pending_date: str | None,
    expected: bool,
) -> None:
    source = (DBT / "models/intermediate/int_enrollment_events.sql").read_text()
    ctes = source[
        source.index("prior_sweep_events AS (") : source.index(
            "eligible_for_enrollment AS ("
        )
    ]
    sql = render_events(
        "WITH "
        + ctes.rstrip().removesuffix(",")
        + " SELECT employee_id FROM auto_enrollment_eligible_population WHERE is_auto_enrollment_eligible",
        simulation_year=year,
    )
    with duckdb.connect() as conn:
        sweep_candidate_inputs(conn, year, optout_date, prior_rate, pending_date)
        assert conn.execute(sql).fetchall() == ([("late_hire",)] if expected else [])
