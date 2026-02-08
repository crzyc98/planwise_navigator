"""
Integration tests for Epic E035 deferral rate escalation events.

Validates that deferral_escalation events in fct_yearly_events follow
business rules: rate cap enforcement, no rate reductions, and event presence.
"""

from pathlib import Path

import pytest

try:
    import duckdb
except ImportError:
    pytest.skip("duckdb not installed", allow_module_level=True)

try:
    from planalign_orchestrator.config import get_database_path
except ImportError:
    get_database_path = None


def _connect():
    """Connect to the simulation database, or skip if unavailable."""
    if get_database_path is not None:
        db_path = get_database_path()
    else:
        db_path = Path("dbt/simulation.duckdb")

    if not db_path.exists():
        pytest.skip(f"Database not found at {db_path}")

    conn = duckdb.connect(str(db_path), read_only=True)

    # Verify fct_yearly_events exists
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    ]
    if "fct_yearly_events" not in tables:
        conn.close()
        pytest.skip("fct_yearly_events table does not exist yet")

    return conn


@pytest.mark.integration
class TestEscalationEventsGenerated:
    """Verify that deferral_escalation events are generated."""

    def test_escalation_events_generated(self):
        """At least one deferral_escalation event should exist after simulation."""
        conn = _connect()
        try:
            result = conn.execute(
                "SELECT COUNT(*) FROM fct_yearly_events "
                "WHERE event_type = 'deferral_escalation'"
            ).fetchone()
            count = result[0]
            assert count > 0, (
                "Expected at least one deferral_escalation event in fct_yearly_events. "
                "Ensure deferral_escalation_enabled is true in simulation_config.yaml "
                "and a simulation has been run."
            )
        finally:
            conn.close()


@pytest.mark.integration
class TestEscalationRateCapEnforced:
    """Verify that no escalation event exceeds the rate cap."""

    def test_escalation_rate_cap_enforced(self):
        """All employee_deferral_rate values must be <= 0.10 (default cap)."""
        conn = _connect()
        try:
            result = conn.execute(
                "SELECT COUNT(*) FROM fct_yearly_events "
                "WHERE event_type = 'deferral_escalation' "
                "AND employee_deferral_rate > 0.1001"
            ).fetchone()
            violations = result[0]
            assert violations == 0, (
                f"Found {violations} deferral_escalation events with "
                "employee_deferral_rate exceeding 10% cap."
            )
        finally:
            conn.close()


@pytest.mark.integration
class TestEscalationNoRateReduction:
    """Verify that escalation events always increase the rate."""

    def test_escalation_no_rate_reduction(self):
        """new_deferral_rate must be > prev_employee_deferral_rate for all events."""
        conn = _connect()
        try:
            result = conn.execute(
                "SELECT COUNT(*) FROM fct_yearly_events "
                "WHERE event_type = 'deferral_escalation' "
                "AND prev_employee_deferral_rate IS NOT NULL "
                "AND employee_deferral_rate <= prev_employee_deferral_rate"
            ).fetchone()
            violations = result[0]
            assert violations == 0, (
                f"Found {violations} deferral_escalation events where the new rate "
                "did not exceed the previous rate."
            )
        finally:
            conn.close()
