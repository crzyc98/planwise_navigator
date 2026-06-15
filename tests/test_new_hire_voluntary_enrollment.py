"""Feature 096: New hires voluntarily enroll in their hire year.

Integration checks against the materialized simulation database that hire-year new hires
are evaluated for voluntary enrollment at the configured demographic rate (not all of them,
not none of them) and that selected new hires enroll in their hire year rather than a later year.

Run after a multi-year simulation has populated ``dbt/simulation.duckdb`` (e.g. ``planalign simulate
2025-2027``). Marked ``integration`` because it reads the full materialized database.
"""

from __future__ import annotations

import duckdb
import pytest

from planalign_orchestrator.config import get_database_path


@pytest.fixture(scope="module")
def conn():
    db_path = get_database_path()
    if not db_path.exists():
        pytest.skip("simulation.duckdb not present; run a simulation first")
    connection = duckdb.connect(str(db_path), read_only=True)
    yield connection
    connection.close()


def _new_hire_voluntary_share(conn) -> list[tuple[int, int, int]]:
    """Return (simulation_year, new_hires, hire_year_voluntary_enrollees) per year."""
    return conn.execute(
        """
        WITH nh AS (
            SELECT employee_id, simulation_year
            FROM fct_yearly_events
            WHERE event_type = 'hire'
        ),
        v AS (
            SELECT DISTINCT employee_id, simulation_year
            FROM fct_yearly_events
            WHERE event_type = 'enrollment'
              AND event_details LIKE 'Voluntary enrollment%'
        )
        SELECT nh.simulation_year,
               COUNT(*) AS new_hires,
               COUNT(v.employee_id) AS enrolled
        FROM nh
        LEFT JOIN v
          ON nh.employee_id = v.employee_id
         AND nh.simulation_year = v.simulation_year
        GROUP BY nh.simulation_year
        ORDER BY nh.simulation_year
        """
    ).fetchall()


@pytest.mark.integration
def test_new_hires_enroll_in_hire_year_at_configured_share(conn):
    """FR-002 / SC-001: a non-zero, sub-100% share of new hires enroll in their hire year."""
    rows = _new_hire_voluntary_share(conn)
    assert rows, "no new hires found in the simulation"
    for year, new_hires, enrolled in rows:
        assert new_hires > 0, f"year {year}: expected new hires"
        # Configured demographic rate must select some, but not all, eligible new hires.
        assert 0 < enrolled < new_hires, (
            f"year {year}: hire-year voluntary enrollees={enrolled} of {new_hires} "
            "must be >0 and <100% (configured share)"
        )


@pytest.mark.integration
def test_no_new_hire_voluntary_enrollment_is_delayed_past_hire_year(conn):
    """SC-003: with immediate eligibility, every new-hire voluntary enrollment lands in the hire year."""
    delayed = conn.execute(
        """
        WITH nh AS (
            SELECT employee_id, simulation_year AS hire_year
            FROM fct_yearly_events
            WHERE event_type = 'hire'
        ),
        v AS (
            SELECT employee_id, simulation_year AS enroll_year
            FROM fct_yearly_events
            WHERE event_type = 'enrollment'
              AND event_details LIKE 'Voluntary enrollment%'
        )
        SELECT COUNT(*)
        FROM v
        JOIN nh ON v.employee_id = nh.employee_id
        WHERE v.enroll_year > nh.hire_year
        """
    ).fetchone()[0]
    assert (
        delayed == 0
    ), f"{delayed} new-hire voluntary enrollments delayed past hire year"


@pytest.mark.integration
def test_each_new_hire_has_single_voluntary_enrollment_event(conn):
    """SC-005: no duplicate/delayed second enrollment event for a new hire."""
    dupes = conn.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT employee_id
            FROM fct_yearly_events
            WHERE event_type = 'enrollment'
              AND event_details LIKE 'Voluntary enrollment%'
              AND employee_id LIKE 'NH_%'
            GROUP BY employee_id
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    assert dupes == 0, f"{dupes} new hires have duplicate voluntary enrollment events"
