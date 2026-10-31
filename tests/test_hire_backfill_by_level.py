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


def render_model(year: int) -> str:
    variables = {"simulation_year": year, "start_year": 2026}
    env = Environment(undefined=StrictUndefined)
    env.globals.update(
        var=lambda name, default=None: variables.get(name, default),
        config=lambda **kwargs: "",
        ref=lambda name: name,
        is_incremental=lambda: False,
        resolve_parameter=lambda *args: "NULL",
        new_hire_salary_index=lambda: "",
    )
    return env.from_string(MODEL.read_text()).render()


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
        employee_hire_date DATE, employee_compensation DOUBLE)""")
    for level, count in enumerate(current, 1):
        conn.execute(
            """INSERT INTO int_employee_compensation_by_year
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
) -> dict[int, tuple[float, int]]:
    with duckdb.connect(":memory:") as conn:
        create_population(conn, current, year)
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
            FROM range(1, 5) AS t(level_id)""")
        rows = conn.execute(f"""SELECT level_id, hiring_distribution, hires_needed
            FROM ({render_model(year)})""").fetchall()
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
