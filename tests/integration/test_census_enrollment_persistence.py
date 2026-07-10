"""Isolated multi-year enrollment continuity scenarios."""

from __future__ import annotations

from decimal import Decimal
import time

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
def enrollment_db():
    conn = duckdb.connect(":memory:")
    conn.execute(
        """CREATE TABLE int_baseline_workforce (
        employee_id VARCHAR, employee_enrollment_date DATE,
        employee_deferral_rate DECIMAL(9, 6), is_enrolled_at_census BOOLEAN)"""
    )
    conn.execute(
        """CREATE TABLE fct_yearly_events (
        event_id VARCHAR, scenario_id VARCHAR, plan_design_id VARCHAR, employee_id VARCHAR,
        event_type VARCHAR, effective_date DATE, simulation_year INTEGER, event_sequence INTEGER,
        event_details VARCHAR, employee_deferral_rate DECIMAL(9, 6))"""
    )
    conn.execute(
        """INSERT INTO int_baseline_workforce VALUES
        ('census-5pct', DATE '2020-01-01', 0.05, true),
        ('never-enrolled', NULL, NULL, false)"""
    )
    yield conn
    conn.close()


@pytest.mark.integration
def test_census_participant_retains_status_and_rate_without_new_enrollment(
    enrollment_db,
):
    EnrollmentDecisionProjection(DirectConnectionManager(enrollment_db)).rebuild(2026)
    row = enrollment_db.execute(
        """SELECT is_enrolled, ever_opted_out, current_deferral_rate,
        latest_event_id FROM enrollment_decision_projection WHERE employee_id = 'census-5pct'"""
    ).fetchone()
    assert row == (True, False, Decimal("0.050000"), None)


@pytest.mark.integration
def test_prior_fact_overrides_census_and_never_enrolled_control_stays_eligible(
    enrollment_db,
):
    enrollment_db.execute(
        """INSERT INTO fct_yearly_events VALUES
      ('optout', 'default', 'default', 'census-5pct', 'enrollment_change', DATE '2025-04-01', 2025, 1, 'Auto-enrollment opt-out', 0.00)"""
    )
    EnrollmentDecisionProjection(DirectConnectionManager(enrollment_db)).rebuild(2026)
    rows = enrollment_db.execute(
        """SELECT employee_id, is_enrolled, ever_opted_out
      FROM enrollment_decision_projection ORDER BY employee_id"""
    ).fetchall()
    assert rows == [("census-5pct", False, True), ("never-enrolled", False, False)]


@pytest.mark.integration
def test_projection_is_scenario_and_plan_scoped(enrollment_db):
    enrollment_db.execute(
        """INSERT INTO fct_yearly_events VALUES
      ('a', 'scenario-a', 'plan-a', 'never-enrolled', 'enrollment', DATE '2025-01-01', 2025, 1, 'Enrollment', 0.04),
      ('b', 'scenario-b', 'plan-b', 'never-enrolled', 'enrollment_change', DATE '2025-02-01', 2025, 1, 'Auto-enrollment opt-out', 0.00)"""
    )
    projection = EnrollmentDecisionProjection(DirectConnectionManager(enrollment_db))
    projection.rebuild(2026, "scenario-a", "plan-a")
    assert enrollment_db.execute(
        "SELECT is_enrolled FROM enrollment_decision_projection WHERE employee_id = 'never-enrolled'"
    ).fetchone() == (True,)
    projection.rebuild(2026, "scenario-b", "plan-b")
    assert enrollment_db.execute(
        "SELECT ever_opted_out FROM enrollment_decision_projection WHERE employee_id = 'never-enrolled'"
    ).fetchone() == (True,)


@pytest.mark.integration
def test_participant_lineage_trace_under_five_minutes(enrollment_db):
    """Reconcile census, authoritative facts, and projection provenance."""
    enrollment_db.execute(
        """INSERT INTO fct_yearly_events VALUES
      ('enroll', 'default', 'default', 'never-enrolled', 'enrollment', DATE '2025-03-01', 2025, 1, 'Enrollment', 0.04)"""
    )
    started = time.monotonic()
    EnrollmentDecisionProjection(DirectConnectionManager(enrollment_db)).rebuild(2026)
    lineage = enrollment_db.execute(
        """SELECT baseline.employee_id,
      baseline.is_enrolled_at_census, fact.event_id, projection.enrollment_source,
      projection.latest_event_id, projection.current_deferral_rate
      FROM int_baseline_workforce baseline
      LEFT JOIN fct_yearly_events fact ON fact.employee_id = baseline.employee_id
      LEFT JOIN enrollment_decision_projection projection ON projection.employee_id = baseline.employee_id
      WHERE baseline.employee_id = 'never-enrolled'"""
    ).fetchone()
    assert lineage == (
        "never-enrolled",
        False,
        "enroll",
        "fct_yearly_events",
        "enroll",
        Decimal("0.040000"),
    )
    assert time.monotonic() - started < 300
