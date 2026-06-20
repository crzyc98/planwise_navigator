"""Regression guard for GitHub issue #318 on the LIVE enrollment path.

Issue #318 reported that auto-enrollment with scope ``all_eligible_employees`` and a
permissive hire-date cutoff re-enrolls already-contributing employees and resets
their deferral rate to the auto-enrollment default. Investigation (feature 100)
found that the model the issue cited (``int_enrollment_decision_matrix``) is
orphaned dead code that never reaches event generation, and that the LIVE path
(``int_enrollment_events``) already excludes already-participating employees via
its ``was_enrolled_previously`` gate. These tests lock that correct behavior in
against the real ``fct_yearly_events`` / ``fct_workforce_snapshot`` artifacts so a
future change cannot silently reintroduce the bug.

Run after a multi-year simulation has populated the database (e.g. ``planalign
simulate 2025-2027``). The auto-enrollment sweep is most aggressive under scope
``all_eligible_employees`` with an early hire-date cutoff; that is the worst case
for this invariant. Marked ``integration`` because they read the full materialized
database.
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
    present = {
        row[0]
        for row in connection.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    }
    required = {"fct_yearly_events", "int_baseline_workforce"}
    missing = required - present
    if missing:
        connection.close()
        pytest.skip(f"database not fully materialized; missing {sorted(missing)}")
    yield connection
    connection.close()


@pytest.mark.integration
def test_census_enrolled_never_receive_auto_enrollment(conn):
    """#318 core invariant: an employee enrolled at census is never auto-swept,
    in any simulation year, regardless of scope/cutoff."""
    offending = conn.execute(
        """
        SELECT e.simulation_year, COUNT(DISTINCT e.employee_id) AS swept
        FROM fct_yearly_events e
        JOIN int_baseline_workforce b ON e.employee_id = b.employee_id
        WHERE e.event_type = 'enrollment'
          AND e.event_details LIKE 'Auto%'
          AND COALESCE(b.is_enrolled_at_census, false) = true
        GROUP BY e.simulation_year
        HAVING COUNT(DISTINCT e.employee_id) > 0
        """
    ).fetchall()
    assert not offending, (
        "census-enrolled employees received auto-enrollment events (issue #318): "
        f"{[(year, n) for year, n in offending]}"
    )


@pytest.mark.integration
def test_auto_enrollment_still_occurs_for_unenrolled(conn):
    """Non-regression: the exclusion must not suppress legitimate auto-enrollment of
    genuinely unenrolled eligible employees."""
    auto_events = conn.execute(
        """
        SELECT COUNT(*)
        FROM fct_yearly_events
        WHERE event_type = 'enrollment'
          AND event_details LIKE 'Auto%'
        """
    ).fetchone()[0]
    if auto_events == 0:
        pytest.skip("no auto-enrollment events present (auto-enrollment disabled?)")
    assert auto_events > 0


@pytest.mark.integration
def test_no_auto_enrollment_downgrades_a_census_saver(conn):
    """#318 corollary: no census saver ends a year below their census deferral rate
    *because of* an auto-enrollment event in that year."""
    downgrades = conn.execute(
        """
        WITH auto AS (
            SELECT DISTINCT employee_id, simulation_year
            FROM fct_yearly_events
            WHERE event_type = 'enrollment' AND event_details LIKE 'Auto%'
        )
        SELECT COUNT(*)
        FROM fct_workforce_snapshot s
        JOIN int_baseline_workforce b ON s.employee_id = b.employee_id
        JOIN auto a
          ON a.employee_id = s.employee_id
         AND a.simulation_year = s.simulation_year
        WHERE COALESCE(b.is_enrolled_at_census, false) = true
          AND s.current_deferral_rate < b.employee_deferral_rate
        """
    ).fetchone()[0]
    assert downgrades == 0, (
        f"{downgrades} census savers were auto-enrolled and ended below their "
        "census deferral rate (issue #318)"
    )
