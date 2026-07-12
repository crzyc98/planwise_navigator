"""Unit coverage for the fact-backed enrollment decision projection."""

from __future__ import annotations

from decimal import Decimal

import duckdb
import pytest

from planalign_orchestrator.pipeline.enrollment_projection import (
    EnrollmentDecisionProjection,
)


class DirectConnectionManager:
    def __init__(self, connection):
        self.connection = connection

    def execute_with_retry(self, callback, **_kwargs):
        return callback(self.connection)


@pytest.fixture
def projection_db():
    conn = duckdb.connect(":memory:")
    conn.execute(
        """CREATE TABLE int_baseline_workforce (
          employee_id VARCHAR, employee_enrollment_date DATE, employee_deferral_rate DECIMAL(9, 6), is_enrolled_at_census BOOLEAN
        )"""
    )
    conn.execute(
        """CREATE TABLE fct_yearly_events (
          event_id VARCHAR, scenario_id VARCHAR, plan_design_id VARCHAR,
          employee_id VARCHAR, event_type VARCHAR, effective_date DATE,
          simulation_year INTEGER, event_sequence INTEGER, event_details VARCHAR, employee_deferral_rate DECIMAL(9, 6)
        )"""
    )
    conn.execute(
        "INSERT INTO int_baseline_workforce VALUES ('baseline', DATE '2020-01-01', 0.05, true), ('new', NULL, NULL, false)"
    )
    yield conn
    conn.close()


@pytest.mark.fast
@pytest.mark.unit
def test_projection_uses_prior_facts_and_preserves_scope(projection_db):
    projection_db.execute(
        """INSERT INTO fct_yearly_events VALUES
          ('enroll-new', 'scenario-a', 'plan-a', 'new', 'enrollment', DATE '2025-02-01', 2025, 1, 'Voluntary enrollment', 0.04),
          ('optout-base', 'scenario-a', 'plan-a', 'baseline', 'enrollment_change', DATE '2025-06-01', 2025, 2, 'Auto-enrollment opt-out', 0.00),
          ('other-scope', 'scenario-b', 'plan-a', 'new', 'enrollment_change', DATE '2025-07-01', 2025, 2, 'Auto-enrollment opt-out', 0.00)
        """
    )
    result = EnrollmentDecisionProjection(
        DirectConnectionManager(projection_db)
    ).rebuild(2026, "scenario-a", "plan-a")

    assert result.employee_count == 2
    rows = projection_db.execute(
        "SELECT employee_id, is_enrolled, ever_opted_out, enrollment_source, current_deferral_rate "
        "FROM enrollment_decision_projection ORDER BY employee_id"
    ).fetchall()
    assert rows == [
        ("baseline", False, True, "fct_yearly_events", Decimal("0.000000")),
        ("new", True, False, "fct_yearly_events", Decimal("0.040000")),
    ]


@pytest.mark.fast
@pytest.mark.unit
def test_projection_excludes_current_year_events(projection_db):
    projection_db.execute(
        """INSERT INTO fct_yearly_events VALUES
          ('future-event', 'scenario-a', 'plan-a', 'new', 'enrollment', DATE '2026-02-01', 2026, 1, 'Voluntary enrollment', 0.04)
        """
    )
    EnrollmentDecisionProjection(DirectConnectionManager(projection_db)).rebuild(
        2026, "scenario-a", "plan-a"
    )

    assert projection_db.execute(
        "SELECT is_enrolled FROM enrollment_decision_projection WHERE employee_id = 'new'"
    ).fetchone() == (False,)


@pytest.mark.fast
@pytest.mark.unit
def test_projection_replay_is_deterministic_and_latest_event_wins(projection_db):
    projection_db.execute(
        """INSERT INTO fct_yearly_events VALUES
      ('enroll', 'default', 'default', 'new', 'enrollment', DATE '2025-01-01', 2025, 1, 'Enrollment', 0.03),
      ('optout', 'default', 'default', 'new', 'enrollment_change', DATE '2025-01-01', 2025, 2, 'Auto-enrollment opt-out', 0.00)"""
    )
    projection = EnrollmentDecisionProjection(DirectConnectionManager(projection_db))
    first = projection.rebuild(2026)
    first_rows = projection_db.execute(
        "SELECT * FROM enrollment_decision_projection ORDER BY employee_id"
    ).fetchall()
    second = projection.rebuild(2026)
    assert first.employee_count == second.employee_count
    assert (
        projection_db.execute(
            "SELECT * FROM enrollment_decision_projection ORDER BY employee_id"
        ).fetchall()
        == first_rows
    )
    assert projection_db.execute(
        "SELECT is_enrolled, ever_opted_out, latest_event_id FROM enrollment_decision_projection WHERE employee_id = 'new'"
    ).fetchone() == (False, True, "optout")


@pytest.mark.fast
@pytest.mark.unit
def test_ensure_table_creates_empty_dbt_source_relation():
    conn = duckdb.connect(":memory:")
    try:
        EnrollmentDecisionProjection(DirectConnectionManager(conn)).ensure_table()

        assert conn.execute(
            "SELECT COUNT(*) FROM enrollment_decision_projection"
        ).fetchone() == (0,)
    finally:
        conn.close()


EXPECTED_PROJECTION_COLUMNS = {
    "employee_id",
    "decision_year",
    "scenario_id",
    "plan_design_id",
    "enrollment_date",
    "is_enrolled",
    "ever_opted_out",
    "enrollment_source",
    "current_deferral_rate",
    "latest_event_id",
    "latest_event_year",
    "latest_event_effective_date",
}


def _projection_columns(conn) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'main' "
            "AND table_name = 'enrollment_decision_projection'"
        ).fetchall()
    }


@pytest.mark.fast
@pytest.mark.unit
def test_ensure_table_recreates_stale_pre_420_schema():
    """A DB built before PR #420 has the 8-column projection; ensure_table
    must drop and recreate it (the table is disposable) instead of leaving a
    schema that stg_prior_enrollment_state cannot bind against."""
    conn = duckdb.connect(":memory:")
    try:
        conn.execute(
            """CREATE TABLE enrollment_decision_projection (
              employee_id VARCHAR,
              decision_year INTEGER,
              scenario_id VARCHAR,
              plan_design_id VARCHAR,
              enrollment_date TIMESTAMP,
              is_enrolled BOOLEAN,
              ever_opted_out BOOLEAN,
              enrollment_source VARCHAR
            )"""
        )
        conn.execute(
            "INSERT INTO enrollment_decision_projection VALUES "
            "('stale', 2025, 'default', 'default', TIMESTAMP '2020-01-01', "
            "true, false, 'baseline_census')"
        )

        EnrollmentDecisionProjection(DirectConnectionManager(conn)).ensure_table()

        assert _projection_columns(conn) == EXPECTED_PROJECTION_COLUMNS
        # Stale rows are discarded with the stale schema; the orchestrator
        # rebuilds the projection before each event-generation year anyway.
        assert conn.execute(
            "SELECT COUNT(*) FROM enrollment_decision_projection"
        ).fetchone() == (0,)
    finally:
        conn.close()


@pytest.mark.fast
@pytest.mark.unit
def test_ensure_table_preserves_current_schema_table_and_rows():
    conn = duckdb.connect(":memory:")
    try:
        projection = EnrollmentDecisionProjection(DirectConnectionManager(conn))
        projection.ensure_table()
        conn.execute(
            "INSERT INTO enrollment_decision_projection VALUES "
            "('kept', 2025, 'default', 'default', DATE '2020-01-01', true, "
            "false, 'baseline_census', 0.05, NULL, NULL, NULL)"
        )

        projection.ensure_table()

        assert _projection_columns(conn) == EXPECTED_PROJECTION_COLUMNS
        assert conn.execute(
            "SELECT COUNT(*) FROM enrollment_decision_projection"
        ).fetchone() == (1,)
    finally:
        conn.close()
