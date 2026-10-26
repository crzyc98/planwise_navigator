"""Execute Easy Enroll selection, escalation, and dbt guards in DuckDB."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol, cast

import duckdb
from jinja2 import Environment, StrictUndefined
from jinja2.nativetypes import NativeEnvironment
import pytest

pytestmark = pytest.mark.fast
DBT = Path(__file__).resolve().parents[2] / "dbt"
PACKAGES = [
    {"rate": 0.04, "share": 0.25},
    {"rate": 0.07, "share": 0.55},
    {"rate": 0.11, "share": 0.20},
]


class EasyEnrollMacros(Protocol):
    def easy_enroll_selected(self, category: str, employee: str, year: int) -> str: ...
    def easy_enroll_package_rate(self, employee: str, year: int) -> str: ...
    def easy_enroll_member(
        self, relation: str, employee: str, year: int, scenario: str
    ) -> str: ...


def _macro_source() -> str:
    return "\n".join(
        (DBT / "macros" / name).read_text()
        for name in (
            "utils/subsystem_seed.sql",
            "self_directed_enrollment_rate.sql",
            "easy_enroll.sql",
            "aip_initial_membership.sql",
            "get_plan_design_parameters.sql",
        )
    )


def _macros(**variables: Any) -> EasyEnrollMacros:
    return cast(
        EasyEnrollMacros,
        NativeEnvironment(undefined=StrictUndefined)
        .from_string(_macro_source())
        .make_module({"var": lambda name, default=None: variables.get(name, default)}),
    )


def _render_sql(source: str, **variables: Any) -> str:
    """Render production SQL; only dbt plumbing and unrelated bands are stubbed."""
    return (
        Environment(undefined=StrictUndefined)
        .from_string(_macro_source() + source)
        .render(
            var=lambda name, default=None: variables.get(name, default),
            ref=lambda name: name,
            config=lambda **kwargs: "",
            is_incremental=lambda: False,
            target={"schema": "main"},
            assign_age_band=lambda column: "'35-44'",
            assign_tenure_band=lambda column: "'0-4'",
        )
    )


@pytest.fixture(scope="module")
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    with duckdb.connect() as conn:
        module = (
            Environment()
            .from_string((DBT / "macros/utils/stable_hash.sql").read_text())
            .module
        )
        conn.execute(getattr(module, "install_stable_hash")())
        yield conn


@pytest.mark.parametrize("ae,share", [(True, 0.57), (False, 0.45)])
def test_channel_and_package_distribution(
    connection: duckdb.DuckDBPyConnection, ae: bool, share: float
) -> None:
    macros = _macros(auto_enrollment_enabled=ae)
    choice = macros.easy_enroll_selected("category", "employee_id", 2025)
    package = macros.easy_enroll_package_rate("employee_id", 2025)
    rows = connection.execute(
        "WITH employees AS (SELECT 'employee-' || i AS employee_id, category "
        "FROM range(10000) t(i) CROSS JOIN (VALUES ('auto_enrollment'), "
        "('enrollment_opt_out'), ('voluntary_enrollment'), ('proactive_voluntary'), "
        "('year_over_year_voluntary')) c(category)) "
        f"SELECT category, {package}, COUNT(*) FROM employees WHERE {choice} "
        "GROUP BY ALL ORDER BY ALL"
    ).fetchall()
    assert {row[0] for row in rows} == {
        "voluntary_enrollment",
        "proactive_voluntary",
        "year_over_year_voluntary",
    }
    for category in {row[0] for row in rows}:
        counts = {float(rate): count for cat, rate, count in rows if cat == category}
        total = sum(counts.values())
        assert abs(total / 10000 - share) < 0.02
        assert counts.keys() == {0.06, 0.08, 0.10}
        for rate, expected in [(0.06, 0.30), (0.08, 0.50), (0.10, 0.20)]:
            assert abs(counts[rate] / total - expected) < 0.03


def test_custom_package_and_share_boundaries(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    for share in (0.0, 1.0):
        macros = _macros(
            easy_enroll_channel_share_with_auto_enrollment=share,
            easy_enroll_packages=[{"rate": 0.075, "share": 1.0}],
        )
        selected = macros.easy_enroll_selected("'voluntary_enrollment'", "'x'", 2025)
        package = macros.easy_enroll_package_rate("'x'", 2025)
        row = connection.execute(f"SELECT {selected}, {package}").fetchone()
        assert row is not None
        assert row[0] == bool(share)
        assert float(row[1]) == 0.075


@pytest.fixture
def winning_enrollments(
    connection: duckdb.DuckDBPyConnection,
) -> duckdb.DuckDBPyConnection:
    """Supply winning channels at the enrollment model's deduplication boundary."""
    connection.execute("""
        CREATE OR REPLACE TABLE deduplicated_events AS
        SELECT category || '-' || i AS employee_id, 'synthetic' AS employee_ssn,
          'enrollment' AS event_type, 2025 AS simulation_year,
          DATE '2025-02-01' AS effective_date, 'fixture' AS event_details,
          50000 AS compensation_amount, 50000 AS previous_compensation,
          0.02 AS employee_deferral_rate, 0.0 AS prev_employee_deferral_rate,
          40 AS employee_age, 2 AS employee_tenure, 1 AS level_id,
          '35-44' AS age_band, '0-4' AS tenure_band, 1.0 AS event_probability,
          category AS event_category, 1 AS priority_rank
        FROM range(4000) t(i) CROSS JOIN (VALUES ('voluntary_enrollment'),
          ('proactive_voluntary'), ('proactive_voluntary_enrollment'),
          ('year_over_year_voluntary'), ('auto_enrollment')) c(category)
    """)
    return connection


def _enrollment_sql(ae: bool, share: float) -> str:
    source = (DBT / "models/intermediate/int_enrollment_events.sql").read_text()
    tail = source[source.index("{% if var('easy_enroll_enabled', false) %}") :]
    return _render_sql(
        "WITH fixture_boundary AS (SELECT 1)\n" + tail,
        easy_enroll_enabled=True,
        auto_enrollment_enabled=ae,
        # Opposite inactive shares catch use of the wrong AE configuration branch.
        easy_enroll_channel_share_with_auto_enrollment=share if ae else 1 - share,
        easy_enroll_channel_share_without_auto_enrollment=1 - share if ae else share,
        easy_enroll_packages=PACKAGES,
    )


@pytest.mark.parametrize("ae", [True, False])
@pytest.mark.parametrize("share", [0.0, 1.0])
def test_enrollment_model_assigns_channel_and_configured_packages(
    winning_enrollments: duckdb.DuckDBPyConnection, ae: bool, share: float
) -> None:
    connection = winning_enrollments
    sql = _enrollment_sql(ae, share)
    connection.execute(f"CREATE OR REPLACE TABLE enrollment_result AS {sql}")
    rows = connection.execute("""
        SELECT d.event_category, e.event_category, e.employee_deferral_rate, COUNT(*)
        FROM enrollment_result e JOIN deduplicated_events d USING (employee_id)
        GROUP BY ALL
    """).fetchall()
    assert sum(count for _, _, _, count in rows) == 20000
    for category in {row[0] for row in rows}:
        counts = {
            float(rate): count
            for original, _, rate, count in rows
            if original == category
        }
        expected_channel = (
            "easy_enroll" if share == 1 and category != "auto_enrollment" else category
        )
        assert {
            channel for original, channel, _, _ in rows if original == category
        } == {expected_channel}
        assert sum(counts.values()) == 4000
        if expected_channel == "easy_enroll":
            assert counts.keys() == {package["rate"] for package in PACKAGES}
            for package in PACKAGES:
                assert abs(counts[package["rate"]] / 4000 - package["share"]) < 0.03
        else:
            assert counts == {0.02: 4000}


@pytest.fixture
def escalation_inputs(
    connection: duckdb.DuckDBPyConnection,
) -> duckdb.DuckDBPyConnection:
    """Two otherwise identical enrollees; only one chose an EE package in 2025."""
    connection.execute("""
        CREATE OR REPLACE TABLE int_enrollment_events AS
        SELECT employee_id, 'default' AS scenario_id, 2025 AS simulation_year,
          'enrollment' AS event_type, category AS event_category,
          0.095 AS employee_deferral_rate, DATE '2025-07-01' AS effective_date
        FROM (VALUES ('member', 'easy_enroll'),
          ('nonmember', 'voluntary_enrollment')) t(employee_id, category);
        CREATE OR REPLACE TABLE int_employee_compensation_by_year AS
        SELECT employee_id, 'synthetic' AS employee_ssn,
          DATE '2024-01-01' AS employee_hire_date, 50000 AS employee_compensation,
          40 AS current_age, 2 AS current_tenure, 1 AS level_id,
          'active' AS employment_status, 2026 AS simulation_year,
          TRUE AS is_enrolled_flag, effective_date AS employee_enrollment_date
        FROM int_enrollment_events;
        CREATE OR REPLACE TABLE int_plan_design_assignment_accumulator AS
        SELECT employee_id, 'default' AS scenario_id, 'default' AS plan_design_id,
          2026 AS simulation_year FROM int_enrollment_events;
        CREATE OR REPLACE TABLE int_deferral_rate_state_accumulator AS
        SELECT employee_id, scenario_id, 'default' AS plan_design_id, simulation_year,
          employee_deferral_rate AS current_deferral_rate,
          TRUE AS is_enrolled_flag,
          event_category = 'easy_enroll' AS aip_participant,
          effective_date AS employee_enrollment_date, NULL::DATE AS last_escalation_date
        FROM int_enrollment_events;
        CREATE OR REPLACE TABLE int_synthetic_baseline_enrollment_events AS
        SELECT employee_id, employee_deferral_rate, effective_date
        FROM int_enrollment_events WHERE FALSE;
        CREATE OR REPLACE TABLE stg_census_data AS
        SELECT employee_id, FALSE AS auto_escalation_opt_out FROM int_enrollment_events;
        CREATE OR REPLACE TABLE int_employee_termination_dates AS
        SELECT employee_id, 2026 AS simulation_year, NULL::DATE AS termination_date
        FROM int_enrollment_events
    """)
    return connection


def _escalation_sql(plan_enabled: bool, **variables: Any) -> str:
    source = (
        DBT / "models/intermediate/events/int_deferral_rate_escalation_events.sql"
    ).read_text()
    return _render_sql(
        source,
        simulation_year=2026,
        start_year=2025,
        easy_enroll_enabled=True,
        deferral_escalation_enabled=plan_enabled,
        deferral_escalation_cap=0.15,
        easy_enroll_escalation_cap=0.10,
        **variables,
    )


def _plan_parameters(increment: float) -> dict[str, Any]:
    return {
        "match": {"cap_percent": 0.06},
        "employer_core": {"contribution_rate": 0.03},
        "auto_enrollment": {
            "default_deferral_rate": 0.06,
            "window_days": 30,
            "scope": "all_eligible_employees",
        },
        "deferral_escalation": {"increment": increment, "cap": 0.15},
        "eligibility": {"waiting_period_days": 0},
    }


def _set_escalation_enrollment(
    connection: duckdb.DuckDBPyConnection, state: str
) -> None:
    connection.execute(
        "UPDATE int_deferral_rate_state_accumulator SET aip_participant = TRUE"
    )
    if state in {
        "missing_after_optout",
        "missing_without_new_enrollment",
        "new_enrollment",
        "reenrollment_after_optout",
    }:
        connection.execute(
            "DELETE FROM int_deferral_rate_state_accumulator WHERE employee_id = 'member'"
        )
    elif state == "unenrolled_positive_rate":
        connection.execute(
            "UPDATE int_deferral_rate_state_accumulator SET is_enrolled_flag = FALSE "
            "WHERE employee_id = 'member'"
        )
    elif state == "enrolled_zero_rate":
        connection.execute(
            "UPDATE int_deferral_rate_state_accumulator SET current_deferral_rate = 0 "
            "WHERE employee_id = 'member'"
        )
    if state in {"missing_after_optout", "latest_optout", "reenrollment_after_optout"}:
        connection.execute("""
            INSERT INTO int_enrollment_events VALUES ('member', 'default', 2025,
              'enrollment_change', 'enrollment_opt_out', 0, DATE '2025-08-01')
        """)
    if state in {"new_enrollment", "reenrollment_after_optout"}:
        connection.execute("""
            INSERT INTO int_enrollment_events VALUES ('member', 'default', 2026,
              'enrollment', 'voluntary_enrollment', 0.06, DATE '2026-01-01')
        """)


@pytest.mark.parametrize("require_enrollment", [True, False])
@pytest.mark.parametrize(
    "state,expected_rate",
    [
        ("missing_after_optout", None),
        ("missing_without_new_enrollment", None),
        ("unenrolled_positive_rate", None),
        ("enrolled_zero_rate", None),
        ("latest_optout", None),
        ("new_enrollment", 0.07),
        ("reenrollment_after_optout", 0.07),
    ],
)
def test_escalation_requires_contributing_enrollment(
    escalation_inputs: duckdb.DuckDBPyConnection,
    require_enrollment: bool,
    state: str,
    expected_rate: float | None,
) -> None:
    connection = escalation_inputs
    _set_escalation_enrollment(connection, state)
    rows = connection.execute(
        _escalation_sql(
            True,
            deferral_escalation_require_enrollment=require_enrollment,
            deferral_escalation_first_delay_years=0,
        )
    ).fetchall()
    events = {row[0]: row for row in rows}
    assert len(rows) == len(events)
    assert events.keys() == {"nonmember"} | (
        {"member"} if expected_rate is not None else set()
    )
    assert float(events["nonmember"][6]) == pytest.approx(0.105)
    if expected_rate is not None:
        assert float(events["member"][6]) == pytest.approx(expected_rate)


@pytest.mark.parametrize(
    "state,enrolled,rate,source,violations",
    [
        (True, True, 0.07, "escalation_event", 0),
        (True, False, 0.07, "carried_forward", 1),
        (True, True, 0.0, "opt_out", 1),
        (False, False, 0.0, "opt_out", 1),
        (True, True, 0.0, "voluntary_change", 0),
    ],
)
def test_singular_escalation_guard_checks_year_end_state(
    state: bool, enrolled: bool, rate: float, source: str, violations: int
) -> None:
    sql = _render_sql(
        (DBT / "tests/assert_escalation_enrolled_state.sql").read_text(),
        simulation_year=2026,
    )
    with duckdb.connect() as connection:
        connection.execute("""
            CREATE TABLE fct_yearly_events AS
            SELECT 'member' AS employee_id, 'default' AS scenario_id,
              'default' AS plan_design_id, 2026 AS simulation_year,
              'deferral_escalation' AS event_type;
            CREATE TABLE int_deferral_rate_state_accumulator (
              employee_id VARCHAR, scenario_id VARCHAR, plan_design_id VARCHAR,
              simulation_year INTEGER, is_enrolled_flag BOOLEAN,
              current_deferral_rate DOUBLE, rate_source VARCHAR
            )
        """)
        if state:
            connection.execute(
                "INSERT INTO int_deferral_rate_state_accumulator VALUES "
                "('member', 'default', 'default', 2026, ?, ?, ?)",
                [enrolled, rate, source],
            )
        assert len(connection.execute(sql).fetchall()) == violations
        connection.execute("UPDATE fct_yearly_events SET scenario_id = 'other'")
        assert connection.execute(sql).fetchall() == []
        connection.execute(
            "UPDATE fct_yearly_events SET scenario_id = 'default', simulation_year = 2025"
        )
        assert connection.execute(sql).fetchall() == []


@pytest.mark.parametrize("plan_enabled", [True, False])
@pytest.mark.parametrize(
    "previous_rate,expected", [(0.08, 0.09), (0.095, 0.10), (0.10, None)]
)
def test_member_receives_next_year_escalation_with_ee_cap(
    escalation_inputs: duckdb.DuckDBPyConnection,
    plan_enabled: bool,
    previous_rate: float,
    expected: float | None,
) -> None:
    connection = escalation_inputs
    connection.execute(
        "UPDATE int_deferral_rate_state_accumulator SET current_deferral_rate = ?",
        [previous_rate],
    )
    # A persisted ordinary AIP election must still be gated by plan enablement.
    connection.execute("""
        UPDATE int_deferral_rate_state_accumulator SET aip_participant = TRUE
        WHERE employee_id = 'nonmember'
    """)
    rows = connection.execute(_escalation_sql(plan_enabled)).fetchall()
    assert connection.description is not None
    columns = [column[0] for column in connection.description]
    events = {row[0]: dict(zip(columns, row)) for row in rows}
    expected_ids = ({"member"} if expected is not None else set()) | (
        {"nonmember"} if plan_enabled else set()
    )
    assert len(rows) == len(expected_ids)
    assert events.keys() == expected_ids
    if plan_enabled:
        assert float(events["nonmember"]["employee_deferral_rate"]) == pytest.approx(
            previous_rate + 0.01
        )
    if expected is not None:
        event = events["member"]
        assert event["event_type"] == "deferral_escalation"
        assert event["simulation_year"] == 2026
        assert float(event["previous_deferral_rate"]) == previous_rate
        assert float(event["employee_deferral_rate"]) == pytest.approx(expected)
        assert float(event["max_escalation_rate"]) == 0.10


@pytest.fixture
def published_events(
    escalation_inputs: duckdb.DuckDBPyConnection,
) -> duckdb.DuckDBPyConnection:
    escalation_inputs.execute("""
        CREATE OR REPLACE TABLE fct_yearly_events AS
        SELECT *, 'original_channel=voluntary_enrollment' AS event_details
        FROM int_enrollment_events
    """)
    return escalation_inputs


@pytest.mark.parametrize("ae", [True, False])
@pytest.mark.parametrize("enabled,share", [(True, 1.0), (True, 0.0), (False, 1.0)])
def test_singular_event_guard_detects_missing_selections(
    published_events: duckdb.DuckDBPyConnection,
    ae: bool,
    enabled: bool,
    share: float,
) -> None:
    connection = published_events
    sql = _render_sql(
        (DBT / "tests/assert_easy_enroll_events.sql").read_text(),
        simulation_year=2025,
        easy_enroll_enabled=enabled,
        auto_enrollment_enabled=ae,
        easy_enroll_channel_share_with_auto_enrollment=share if ae else 1 - share,
        easy_enroll_channel_share_without_auto_enrollment=1 - share if ae else share,
        easy_enroll_packages=[{"rate": 0.095, "share": 1.0}],
    )
    if enabled:
        assert connection.execute(sql).fetchall() == []
    # Suppress all EE selection but leave the self-directed source population.
    connection.execute(
        "UPDATE fct_yearly_events SET event_category = 'voluntary_enrollment'"
    )
    rows = connection.execute(sql).fetchall()
    assert len(rows) == int(enabled and share > 0)
    # A historical EE event or one from another scenario cannot mask the loss.
    connection.execute("""
        INSERT INTO fct_yearly_events
        SELECT employee_id, scenario_id, 2024, event_type, 'easy_enroll',
          employee_deferral_rate, effective_date, 'original_channel=voluntary_enrollment'
        FROM int_enrollment_events WHERE employee_id = 'member';
        INSERT INTO fct_yearly_events
        SELECT employee_id, 'other', simulation_year, event_type, 'easy_enroll',
          employee_deferral_rate, effective_date, 'original_channel=voluntary_enrollment'
        FROM int_enrollment_events WHERE employee_id = 'member'
    """)
    if enabled:
        assert len(connection.execute(sql).fetchall()) == int(share > 0)
    connection.execute("DELETE FROM fct_yearly_events")
    assert connection.execute(sql).fetchall() == []


@pytest.mark.parametrize("plan_enabled", [True, False])
@pytest.mark.parametrize("design_increment", [None, 0.02])
def test_singular_membership_guard_detects_missing_escalation(
    published_events: duckdb.DuckDBPyConnection,
    plan_enabled: bool,
    design_increment: float | None,
) -> None:
    connection = published_events
    variables = (
        {"plan_design_parameters": {"default": _plan_parameters(design_increment)}}
        if design_increment is not None
        else {}
    )
    sql = _render_sql(
        (DBT / "tests/assert_easy_enroll_membership_and_cap.sql").read_text(),
        simulation_year=2026,
        easy_enroll_enabled=True,
        deferral_escalation_enabled=plan_enabled,
        **variables,
    )
    assert connection.execute(sql).fetchall() == [
        ("member", 2026, "missing_escalation")
    ]
    connection.execute("""
        INSERT INTO fct_yearly_events
        SELECT employee_id, scenario_id, 2026, 'deferral_escalation',
          'deferral_escalation', 0.10, DATE '2026-01-01', 'fixture'
        FROM int_enrollment_events WHERE employee_id = 'member'
    """)
    assert connection.execute(sql).fetchall() == []


@pytest.mark.parametrize(
    "exclusion",
    [
        "cap",
        "unenrolled",
        "inactive",
        "delay",
        "cutoff",
        "termination",
        "zero_increment",
        "zero_design_increment",
        "already_escalated",
        "january_effective",
    ],
)
def test_singular_membership_guard_allows_ineligible_members(
    published_events: duckdb.DuckDBPyConnection,
    exclusion: str,
) -> None:
    connection = published_events
    variables: dict[str, Any] = {}
    if exclusion == "cap":
        connection.execute(
            "UPDATE int_deferral_rate_state_accumulator SET current_deferral_rate = 0.10"
        )
    elif exclusion == "unenrolled":
        connection.execute(
            "UPDATE int_employee_compensation_by_year SET is_enrolled_flag = FALSE"
        )
    elif exclusion == "inactive":
        connection.execute(
            "UPDATE int_employee_compensation_by_year SET employment_status = 'terminated'"
        )
    elif exclusion == "delay":
        variables["deferral_escalation_first_delay_years"] = 2
    elif exclusion == "cutoff":
        variables["deferral_escalation_hire_date_cutoff"] = "2025-01-01"
    elif exclusion == "zero_increment":
        variables["deferral_escalation_increment"] = 0.0
    elif exclusion == "zero_design_increment":
        variables["plan_design_parameters"] = {"default": _plan_parameters(0.0)}
    elif exclusion == "already_escalated":
        connection.execute(
            "UPDATE int_deferral_rate_state_accumulator "
            "SET last_escalation_date = DATE '2026-01-01'"
        )
    elif exclusion == "january_effective":
        # A December hire's 2025 election takes effect after the 2026 escalation.
        connection.execute(
            "UPDATE fct_yearly_events SET effective_date = DATE '2026-01-20'"
        )
    else:
        connection.execute("""
            INSERT INTO fct_yearly_events
            SELECT employee_id, scenario_id, 2026, 'termination', 'termination',
              NULL, DATE '2025-12-31', 'fixture'
            FROM int_enrollment_events WHERE employee_id = 'member'
        """)
    sql = _render_sql(
        (DBT / "tests/assert_easy_enroll_membership_and_cap.sql").read_text(),
        simulation_year=2026,
        easy_enroll_enabled=True,
        deferral_escalation_enabled=False,
        **variables,
    )
    assert connection.execute(sql).fetchall() == []


def test_seed_controls_both_draws(connection: duckdb.DuckDBPyConnection) -> None:
    def draws(**variables: Any) -> list[tuple[bool, float]]:
        macros = _macros(**variables)
        choice = macros.easy_enroll_selected(
            "'voluntary_enrollment'", "employee_id", 2025
        )
        package = macros.easy_enroll_package_rate("employee_id", 2025)
        return connection.execute(
            f"SELECT {choice}, {package} FROM (SELECT 'employee-' || i AS employee_id "
            "FROM range(1000) t(i))"
        ).fetchall()

    baseline = draws(random_seed=42)
    assert baseline == draws(random_seed=42)
    assert baseline != draws(random_seed=43)
    assert baseline == draws(random_seed=43, random_seed_deferral_behavior=42)


def test_membership_is_temporal_and_scenario_scoped(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    sql = _macros().easy_enroll_member("events", "'employee'", 2026, "'scenario'")
    for scenario, year, category, expected in [
        ("scenario", 2025, "easy_enroll", True),
        ("scenario", 2026, "easy_enroll", True),
        ("scenario", 2027, "easy_enroll", False),
        ("other", 2025, "easy_enroll", False),
        ("scenario", 2025, "auto_enrollment", False),
    ]:
        row = connection.execute(
            "WITH events AS (SELECT 'employee' AS employee_id, ? AS scenario_id, "
            "? AS simulation_year, ? AS event_category, 'enrollment' AS event_type) "
            f"SELECT {sql}",
            [scenario, year, category],
        ).fetchone()
        assert row is not None
        assert row[0] == expected


def test_disabled_escalation_keeps_empty_schema_without_dependencies() -> None:
    source = (
        DBT / "models/intermediate/events/int_deferral_rate_escalation_events.sql"
    ).read_text()
    sql = (
        Environment(undefined=StrictUndefined)
        .from_string(source)
        .render(
            var=lambda name, default=None: {
                "simulation_year": 2025,
                "deferral_escalation_enabled": False,
            }.get(name, default),
            config=lambda **kwargs: "",
        )
    )
    assert "WHERE FALSE" in sql
    assert "WITH parameter_rows" not in sql
