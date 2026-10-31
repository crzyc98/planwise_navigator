"""Exercise the production level allocation SQL against in-memory reference tables."""

from pathlib import Path

import duckdb
import pytest
from jinja2 import Environment, StrictUndefined

pytestmark = pytest.mark.fast
MODEL = (
    Path(__file__).resolve().parents[1]
    / "dbt/models/intermediate/int_workforce_needs_by_level.sql"
)


def render_model(year: int, multiplier: float = 1.0) -> str:
    variables = {
        "simulation_year": year,
        "start_year": 2026,
        "promotion_rate_multiplier": multiplier,
    }
    env = Environment(undefined=StrictUndefined)
    env.globals.update(
        var=lambda name, default=None: variables.get(name, default),
        config=lambda **kwargs: "",
        ref=lambda name: name,
        is_incremental=lambda: False,
        resolve_parameter=lambda *args: "NULL",
        new_hire_salary_index=lambda: "",
        run_query=lambda query: None,
    )
    bands = MODEL.parents[2] / "macros/bands"
    macros = "\n".join(
        (bands / name).read_text()
        for name in ("assign_age_band.sql", "assign_tenure_band.sql")
    )
    return env.from_string(macros + MODEL.read_text()).render()


def create_population(
    conn: duckdb.DuckDBPyConnection, current: tuple[int, ...], year: int
) -> None:
    conn.execute("""CREATE TABLE int_baseline_workforce AS
        SELECT level_id, 2026 AS simulation_year, 'active' AS employment_status
        FROM (VALUES (1, 60), (2, 30), (3, 10)) AS t(level_id, n),
        LATERAL range(n)""")
    # Distractors must not affect the frozen active start-year anchor.
    conn.execute(
        "INSERT INTO int_baseline_workforce VALUES (4, 2026, 'terminated'), (4, 2027, 'active')"
    )
    conn.execute("""CREATE TABLE int_employee_compensation_by_year (
        level_id INTEGER, simulation_year INTEGER, employment_status VARCHAR,
        employee_hire_date DATE, employee_compensation DOUBLE,
        current_age INTEGER DEFAULT 40, current_tenure INTEGER DEFAULT 5)""")
    for level, count in enumerate(current, 1):
        conn.execute(
            """INSERT INTO int_employee_compensation_by_year
            (level_id, simulation_year, employment_status, employee_hire_date, employee_compensation)
            SELECT ?, ?, 'active', DATE '2020-01-01', 80000 FROM range(?)""",
            [level, year, count],
        )


def allocate(
    current: tuple[int, ...],
    *,
    year: int = 2027,
    fixed: bool = False,
    hires: int = 20,
    target: int = 105,
    terms: int = 10,
    promotion_rate: float = 0.0,
    multiplier: float = 1.0,
) -> dict[int, tuple[float, int]]:
    with duckdb.connect(":memory:") as conn:
        create_population(conn, current, year)
        create_hazards(conn, year, promotion_rate)
        conn.execute(
            """CREATE TABLE int_workforce_needs AS SELECT
            'test' AS workforce_needs_id, 'default' AS scenario_id, ? AS simulation_year,
            ? AS expected_experienced_terminations, ? AS total_hires_needed,
            ? AS target_ending_workforce, 0.25 AS new_hire_termination_rate""",
            [year, terms, hires, target],
        )
        conn.execute(
            """CREATE TABLE config_new_hire_level_distribution AS SELECT
            'default' AS scenario_id, level_id, distribution_pct, ? AS use_fixed_distribution
            FROM (VALUES (1, 0.2), (2, 0.3), (3, 0.5)) AS t(level_id, distribution_pct)""",
            [fixed],
        )
        conn.execute("""CREATE TABLE stg_config_job_levels AS SELECT
            level_id, 50000 AS min_compensation, 100000 AS max_compensation
            FROM range(1, 6) AS t(level_id)""")
        rows = conn.execute(f"""SELECT level_id, hiring_distribution, hires_needed
            FROM ({render_model(year, multiplier)})""").fetchall()
    result = {level: (share, count) for level, share, count in rows}
    assert sum(count for _, count in result.values()) == hires
    return result


def test_first_year_matches_census() -> None:
    result = allocate((60, 30, 10), year=2026)
    for level, share in enumerate((0.6, 0.3, 0.1), 1):
        assert result[level][0] == pytest.approx(share)
        assert abs(result[level][1] - 20 * share) <= 1


def test_underfilled_level_gets_backfill() -> None:
    result = allocate((40, 40, 20))
    assert result[1] == (1.0, 20)
    assert result[2] == (0.0, 0)
    assert result[3] == (0.0, 0)


def test_empty_census_level_receives_hires() -> None:
    result = allocate((0, 70, 30))
    assert result[1] == (1.0, 20)


def test_fixed_distribution_takes_precedence() -> None:
    result = allocate((40, 40, 20), fixed=True)
    for level, share in enumerate((0.2, 0.3, 0.5), 1):
        assert result[level][0] == pytest.approx(share)
        assert result[level][1] == round(20 * share)


def test_level_absent_from_census_gets_no_hires() -> None:
    assert allocate((40, 30, 20, 10))[4] == (0.0, 0)


def test_zero_gap_falls_back_to_anchor() -> None:
    result = allocate((60, 30, 10), target=90, hires=0)
    assert [result[level][0] for level in (1, 2, 3)] == pytest.approx([0.6, 0.3, 0.1])


@pytest.mark.parametrize("hires", [1, 7, 23, 101])
def test_slot_rounding_preserves_total(hires: int) -> None:
    allocate((60, 30, 10), hires=hires)


def create_hazards(conn: duckdb.DuckDBPyConnection, year: int, rate: float) -> None:
    conn.execute(
        """CREATE TABLE int_hazard_promotion AS
        SELECT level_id, ? AS year, '35-44' AS age_band,
        '5-9' AS tenure_band, ? AS promotion_rate
        FROM range(1, 6) t(level_id)""",
        [year, rate],
    )


def test_expected_promotions_shift_hires_to_losing_level() -> None:
    old = allocate((60, 30, 10))
    actual = allocate((60, 30, 10), promotion_rate=0.1)
    # Expected flows 6, 3, 1 turn old gaps 9, 4.5, 1.5 into 15, 1.5, 0.
    assert actual[1][0] == pytest.approx(15 / 16.5)
    assert actual[2][0] == pytest.approx(1.5 / 16.5)
    assert actual[1][1] > old[1][1]
    assert actual[2][1] < old[2][1]


def test_zero_promotion_rates_match_old_formula() -> None:
    actual = allocate((60, 30, 10), promotion_rate=0.0)
    for level, expected in {1: (0.6, 12), 2: (0.3, 6), 3: (0.1, 2)}.items():
        assert actual[level][0] == pytest.approx(expected[0])
        assert actual[level][1] == expected[1]


def test_top_level_has_no_outflow_even_with_positive_hazard() -> None:
    with duckdb.connect(":memory:") as conn:
        create_population(conn, (1, 1, 1, 1, 10), 2027)
        create_hazards(conn, 2027, 0.2)
        sql = render_model(2027)
        flows = sql[
            sql.index("promotion_eligible_workforce AS") : sql.index(
                "-- Backfill toward"
            )
        ]
        rows = conn.execute(
            "WITH "
            + flows.rstrip().rstrip(",")
            + " SELECT level_id, promotions_out FROM expected_promotion_flows ORDER BY level_id"
        ).fetchall()
    assert rows == [(1, 0.2), (2, 0.2), (3, 0.2), (4, 0.2)]


def test_multiplier_and_probability_cap() -> None:
    assert allocate((60, 30, 10), promotion_rate=0.2, multiplier=0) == allocate(
        (60, 30, 10)
    )
    assert allocate((60, 30, 10), promotion_rate=0.8, multiplier=2) == allocate(
        (60, 30, 10), promotion_rate=1
    )


def test_fixed_distribution_ignores_promotion_flows() -> None:
    assert allocate((60, 30, 10), fixed=True, promotion_rate=0.2) == allocate(
        (60, 30, 10), fixed=True
    )


@pytest.mark.parametrize(
    "column,value",
    [
        ("current_age", "65"),
        ("current_tenure", "0"),
        ("employment_status", "'terminated'"),
        ("simulation_year", "2026"),
    ],
)
def test_ineligible_employees_have_no_expected_outflow(column: str, value: str) -> None:
    with duckdb.connect(":memory:") as conn:
        create_population(conn, (10,), 2027)
        create_hazards(conn, 2027, 0.2)
        conn.execute(f"UPDATE int_employee_compensation_by_year SET {column} = {value}")
        sql = render_model(2027)
        flows = sql[
            sql.index("promotion_eligible_workforce AS") : sql.index(
                "-- Backfill toward"
            )
        ]
        rows = conn.execute(
            "WITH "
            + flows.rstrip().rstrip(",")
            + " SELECT level_id, promotions_out FROM expected_promotion_flows"
        ).fetchall()
    assert rows == []
