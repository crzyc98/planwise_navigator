"""Execute production hiring SQL with synthetic cohorts and the frozen hash."""

from datetime import date
from pathlib import Path

import duckdb
import pytest
from jinja2 import Environment

pytestmark = pytest.mark.fast
DBT = Path(__file__).resolve().parents[1] / "dbt"


def render_hiring(year: int, seed: int = 42, legacy: bool = False) -> str:
    env = Environment()
    env.globals.update(
        var=lambda name, default=None: {
            "simulation_year": year,
            "new_hire_age_distribution": [{"age": 32, "weight": 1.0}],
        }.get(name, default),
        config=lambda **kwargs: "",
        ref=lambda name: name,
        subsystem_seed=lambda name: seed,
        assign_age_band=lambda column: "'age_band'",
        assign_tenure_band=lambda column: "'tenure_band'",
    )
    macro = env.from_string(
        (DBT / "macros/events/distributed_hire_date.sql").read_text()
    ).module
    env.globals["distributed_hire_date"] = macro.distributed_hire_date
    source = (DBT / "models/intermediate/events/int_hiring_events.sql").read_text()
    if legacy:
        source = source.replace(
            "{{ distributed_hire_date('hwa.hire_sequence_num', simulation_year) }}",
            "CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL (hwa.hire_sequence_num % 365) DAY",
        )
    return env.from_string(source).render()


def setup_cohort(conn: duckdb.DuckDBPyConnection, year: int, count: int) -> None:
    hash_source = (DBT / "macros/utils/stable_hash.sql").read_text()
    conn.execute(Environment().from_string(hash_source).module.install_stable_hash())
    conn.execute(
        """CREATE TABLE int_workforce_needs AS SELECT
        1 workforce_needs_id, 'default' scenario_id, ? simulation_year,
        ? total_hires_needed, 0 starting_workforce_count, 0 target_growth_rate,
        0 expected_experienced_terminations, 0 expected_new_hire_terminations,
        0 calculated_net_change, 0 target_ending_workforce""",
        [year, count],
    )
    conn.execute(
        """CREATE TABLE int_workforce_needs_by_level AS SELECT
        level_id, COUNT(*) hires_needed, 50000 + level_id * 10000 new_hire_avg_compensation,
        ? simulation_year, 'default' scenario_id
        FROM (SELECT 1 + i % 5 level_id FROM range(?) t(i)) GROUP BY level_id""",
        [year, count],
    )


@pytest.mark.parametrize("year", [2025, 2028])
@pytest.mark.parametrize("count", [0, 1, 365, 366, 938, 1079])
def test_hiring_calendar_distribution(year: int, count: int) -> None:
    with duckdb.connect(":memory:") as conn:
        setup_cohort(conn, year, count)
        conn.execute("CREATE TABLE hires AS " + render_hiring(year))
        rows = conn.execute("SELECT * FROM hires ORDER BY employee_id").fetchall()
        assert len(rows) == count
        assert rows == conn.execute(render_hiring(year)).fetchall()
        # All non-date attributes retain their exact pre-fix assignments.
        old = conn.execute(render_hiring(year, legacy=True)).fetchall()
        assert [r[:4] + r[5:] for r in rows] == [r[:4] + r[5:] for r in old]
        if not count:
            return
        days = (date(year + 1, 1, 1) - date(year, 1, 1)).days
        dates = [r[4].date() for r in rows]
        assert all(date(year, 1, 1) <= d < date(year + 1, 1, 1) for d in dates)
        mean_day = sum(d.timetuple().tm_yday for d in dates) / count
        assert abs(mean_day - (days + 1) / 2) <= 0.5
        assert (
            conn.execute(
                """SELECT COUNT(*) FROM (
            SELECT level_id FROM hires GROUP BY level_id HAVING COUNT(*) >= 20
            AND NOT (MIN(DAYOFYEAR(effective_date)) <= ?
                     AND MAX(DAYOFYEAR(effective_date)) > ?))""",
                [days / 2, days / 2],
            ).fetchone()[0]
            == 0
        )
        if count >= days:
            assert date(year, 12, 31) in dates
            if days == 366:
                assert date(year, 2, 29) in dates
        if count > 1:
            assert rows != conn.execute(render_hiring(year, seed=17)).fetchall()


@pytest.mark.parametrize("year", [2025, 2028])
def test_new_hire_terminations_follow_distributed_hires(year: int) -> None:
    with duckdb.connect(":memory:") as conn:
        setup_cohort(conn, year, 1079)
        conn.execute(
            "ALTER TABLE int_workforce_needs ADD COLUMN new_hire_termination_rate DOUBLE DEFAULT 0.25"
        )
        conn.execute(
            "UPDATE int_workforce_needs SET expected_new_hire_terminations = 270"
        )
        conn.execute("CREATE TABLE int_hiring_events AS " + render_hiring(year))
        source = (
            DBT / "models/intermediate/events/int_new_hire_termination_events.sql"
        ).read_text()
        sql = (
            Environment()
            .from_string(source)
            .render(
                var=lambda name, default=None: (
                    year if name == "simulation_year" else default
                ),
                config=lambda **kwargs: "",
                ref=lambda name: name,
                subsystem_seed=lambda name: 42,
                assign_age_band=lambda column: "'age_band'",
                assign_tenure_band=lambda column: "'tenure_band'",
            )
        )
        conn.execute("CREATE TABLE terminations AS " + sql)
        assert conn.execute("SELECT COUNT(*) FROM terminations").fetchone()[0] == 270
        assert (
            conn.execute(
                """SELECT COUNT(*) FROM terminations t
            JOIN int_hiring_events h USING (employee_id)
            WHERE t.effective_date <= h.effective_date
               OR YEAR(t.effective_date) != ?""",
                [year],
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize(
    "path, sequence",
    [
        ("macros/events/events_hire_sql.sql", "hs.hire_sequence_num"),
        (
            "models/intermediate/int_new_hire_compensation_staging.sql",
            "hs.hire_sequence_num",
        ),
    ],
)
def test_mirrored_hiring_dates_use_same_calendar(path: str, sequence: str) -> None:
    """Execute each mirror's actual date expression over the same sequence cohort."""
    source = (DBT / path).read_text()
    expression = next(
        line.strip().removesuffix(" AS hire_date,")
        for line in source.splitlines()
        if " AS hire_date," in line
    )
    env = Environment()
    env.globals["subsystem_seed"] = lambda name: 42
    macro = env.from_string(
        (DBT / "macros/events/distributed_hire_date.sql").read_text()
    ).module
    sql = env.from_string(expression).render(
        distributed_hire_date=macro.distributed_hire_date,
        simulation_year=2028,
    )
    with duckdb.connect(":memory:") as conn:
        setup_cohort(conn, 2028, 938)
        actual = conn.execute(
            f"SELECT {sql} FROM (SELECT i hire_sequence_num FROM range(1, 939) t(i)) hs "
            f"ORDER BY {sequence}"
        ).fetchall()
        expected = [(r[4],) for r in conn.execute(render_hiring(2028)).fetchall()]
        assert actual == expected
