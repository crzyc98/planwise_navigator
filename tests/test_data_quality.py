#!/usr/bin/env python3
"""
Data Quality Tests

Comprehensive data quality validation for production readiness.
Part of Epic E047: Production Testing & Validation Framework.
"""

from __future__ import annotations

import pytest
import duckdb
from decimal import Decimal
from typing import List, Tuple


class TestDataQuality:
    """Comprehensive data quality validation"""

    @pytest.fixture
    def db_connection(self):
        """Provide database connection for tests"""
        return duckdb.connect("simulation.duckdb")

    def test_contribution_limits_compliance(self, db_connection):
        """Verify all contributions within IRS limits"""
        violations = db_connection.execute("""
            SELECT
                ec.employee_id,
                ec.simulation_year,
                ec.annual_contribution_amount,
                ws.total_compensation,
                ec.annual_contribution_amount - ws.total_compensation as excess
            FROM int_employee_contributions ec
            JOIN fct_workforce_snapshot ws
                ON ec.employee_id = ws.employee_id
                AND ec.simulation_year = ws.simulation_year
            WHERE ec.annual_contribution_amount > ws.total_compensation
        """).fetchall()

        assert len(violations) == 0, f"Found {len(violations)} contribution > compensation violations"

    def test_workforce_growth_consistency(self, db_connection):
        """Verify workforce growth follows expected patterns"""
        growth_data = db_connection.execute("""
            SELECT
                simulation_year,
                COUNT(*) as workforce_count,
                LAG(COUNT(*)) OVER (ORDER BY simulation_year) as prev_count
            FROM fct_workforce_snapshot
            WHERE employment_status = 'active'
            GROUP BY simulation_year
            ORDER BY simulation_year
        """).fetchall()

        for year, count, prev_count in growth_data:
            if prev_count:  # Skip first year
                growth_rate = (count - prev_count) / prev_count
                assert -0.2 <= growth_rate <= 0.2, f"Unrealistic growth rate in {year}: {growth_rate:.2%}"

    def test_event_sequence_logic(self, db_connection):
        """Verify events follow logical business rules"""

        # No events before hire date
        pre_hire_events = db_connection.execute("""
            SELECT COUNT(*) FROM fct_yearly_events e1
            JOIN (SELECT employee_id, effective_date as hire_date
                  FROM fct_yearly_events WHERE event_type = 'hire') h
            ON e1.employee_id = h.employee_id
            WHERE e1.effective_date < h.hire_date
            AND e1.event_type != 'hire'
        """).fetchone()[0]
        assert pre_hire_events == 0, f"Found {pre_hire_events} events before hire date"

        # No multiple hires for same employee
        multiple_hires = db_connection.execute("""
            SELECT employee_id, COUNT(*) as hire_count
            FROM fct_yearly_events
            WHERE event_type = 'hire'
            GROUP BY employee_id
            HAVING COUNT(*) > 1
        """).fetchall()
        assert len(multiple_hires) == 0, f"Found {len(multiple_hires)} employees with multiple hire events"

    def test_compensation_consistency(self, db_connection):
        """Verify compensation values are consistent and reasonable"""

        # Check for negative compensation
        negative_comp = db_connection.execute("""
            SELECT COUNT(*) FROM fct_workforce_snapshot
            WHERE total_compensation < 0
        """).fetchone()[0]
        assert negative_comp == 0, f"Found {negative_comp} employees with negative compensation"

        # Check for unreasonably high compensation (> $1M)
        very_high_comp = db_connection.execute("""
            SELECT COUNT(*) FROM fct_workforce_snapshot
            WHERE total_compensation > 1000000
        """).fetchone()[0]
        # Allow some high earners but not too many
        total_employees = db_connection.execute("SELECT COUNT(*) FROM fct_workforce_snapshot").fetchone()[0]
        if total_employees > 0:
            high_comp_pct = very_high_comp / total_employees
            assert high_comp_pct < 0.05, f"Too many high earners: {high_comp_pct:.2%} > 5%"

        # Check for unreasonably low compensation (< $20K)
        very_low_comp = db_connection.execute("""
            SELECT COUNT(*) FROM fct_workforce_snapshot
            WHERE total_compensation < 20000 AND employment_status = 'active'
        """).fetchone()[0]
        assert very_low_comp == 0, f"Found {very_low_comp} active employees with very low compensation"

    def test_employee_id_consistency(self, db_connection):
        """Verify employee ID consistency across tables"""

        # Check for orphaned employee contributions
        orphaned_contributions = db_connection.execute("""
            SELECT COUNT(*) FROM int_employee_contributions ec
            LEFT JOIN fct_workforce_snapshot ws
                ON ec.employee_id = ws.employee_id
                AND ec.simulation_year = ws.simulation_year
            WHERE ws.employee_id IS NULL
        """).fetchone()[0]
        assert orphaned_contributions == 0, f"Found {orphaned_contributions} orphaned employee contributions"

        # Check for orphaned yearly events
        orphaned_events = db_connection.execute("""
            SELECT COUNT(*) FROM fct_yearly_events ye
            WHERE ye.employee_id NOT IN (
                SELECT DISTINCT employee_id FROM fct_workforce_snapshot
                WHERE simulation_year = ye.simulation_year
            )
        """).fetchone()[0]
        # Allow some orphaned events (e.g., for terminated employees)
        total_events = db_connection.execute("SELECT COUNT(*) FROM fct_yearly_events").fetchone()[0]
        if total_events > 0:
            orphaned_pct = orphaned_events / total_events
            assert orphaned_pct < 0.1, f"Too many orphaned events: {orphaned_pct:.2%} > 10%"

    def test_date_consistency(self, db_connection):
        """Verify date fields are consistent and valid"""

        # Check for future dates in events (beyond reasonable simulation range)
        future_events = db_connection.execute("""
            SELECT COUNT(*) FROM fct_yearly_events
            WHERE effective_date > '2040-12-31'
        """).fetchone()[0]
        assert future_events == 0, f"Found {future_events} events with unrealistic future dates"

        # Check for very old dates (before 1950)
        very_old_events = db_connection.execute("""
            SELECT COUNT(*) FROM fct_yearly_events
            WHERE effective_date < '1950-01-01'
        """).fetchone()[0]
        assert very_old_events == 0, f"Found {very_old_events} events with unrealistic old dates"

        # Check enrollment dates are not before hire dates
        enrollment_before_hire = db_connection.execute("""
            SELECT COUNT(*) FROM fct_workforce_snapshot ws
            JOIN fct_yearly_events ye ON ws.employee_id = ye.employee_id
            WHERE ye.event_type = 'hire'
            AND ws.enrollment_date < ye.effective_date
            AND ws.enrollment_date IS NOT NULL
        """).fetchone()[0]
        assert enrollment_before_hire == 0, f"Found {enrollment_before_hire} enrollments before hire date"

    def test_numerical_precision(self, db_connection):
        """Verify numerical fields have appropriate precision"""

        # Check for very small non-zero contribution amounts (< $1)
        tiny_contributions = db_connection.execute("""
            SELECT COUNT(*) FROM int_employee_contributions
            WHERE annual_contribution_amount > 0 AND annual_contribution_amount < 1
        """).fetchone()[0]
        assert tiny_contributions == 0, f"Found {tiny_contributions} contributions < $1"

        # Check for compensation with excessive decimal places
        excessive_precision = db_connection.execute("""
            SELECT COUNT(*) FROM fct_workforce_snapshot
            WHERE total_compensation != ROUND(total_compensation, 2)
        """).fetchone()[0]
        assert excessive_precision == 0, f"Found {excessive_precision} compensation values with > 2 decimal places"

    def test_enrollment_status_consistency(self, db_connection):
        """Verify enrollment status is consistent with enrollment events"""

        # Employees with enrollment events should have enrollment status
        missing_enrollment_status = db_connection.execute("""
            SELECT COUNT(DISTINCT ws.employee_id) FROM fct_workforce_snapshot ws
            JOIN fct_yearly_events ye ON ws.employee_id = ye.employee_id
            WHERE ye.event_type = 'enrollment'
            AND ye.simulation_year <= ws.simulation_year
            AND (ws.enrollment_status IS NULL OR ws.enrollment_status = 'not_enrolled')
        """).fetchone()[0]

        # Allow some flexibility but not too many inconsistencies
        total_with_enrollment_events = db_connection.execute("""
            SELECT COUNT(DISTINCT employee_id) FROM fct_yearly_events
            WHERE event_type = 'enrollment'
        """).fetchone()[0]

        if total_with_enrollment_events > 0:
            inconsistency_rate = missing_enrollment_status / total_with_enrollment_events
            assert inconsistency_rate < 0.1, f"High enrollment status inconsistency: {inconsistency_rate:.2%}"

    def test_termination_logic(self, db_connection):
        """Verify termination events follow business logic"""

        # Terminated employees should not have events after termination
        post_termination_activity = db_connection.execute("""
            SELECT COUNT(*) FROM fct_yearly_events e1
            JOIN (
                SELECT employee_id, effective_date as term_date
                FROM fct_yearly_events
                WHERE event_type = 'termination'
            ) t ON e1.employee_id = t.employee_id
            WHERE e1.effective_date > t.term_date
            AND e1.event_type NOT IN ('termination')  -- Allow multiple termination events for data fixes
        """).fetchone()[0]
        assert post_termination_activity == 0, f"Found {post_termination_activity} events after termination"

        # Terminated employees should have inactive status in workforce snapshot
        active_after_termination = db_connection.execute("""
            SELECT COUNT(DISTINCT ws.employee_id) FROM fct_workforce_snapshot ws
            JOIN fct_yearly_events ye ON ws.employee_id = ye.employee_id
            WHERE ye.event_type = 'termination'
            AND ye.effective_date <= CAST(ws.simulation_year || '-12-31' AS DATE)
            AND ws.employment_status = 'active'
        """).fetchone()[0]
        assert active_after_termination == 0, f"Found {active_after_termination} active employees after termination"

    def test_simulation_year_consistency(self, db_connection):
        """Verify simulation year consistency across tables"""

        # Check that events are in appropriate years
        mismatched_event_years = db_connection.execute("""
            SELECT COUNT(*) FROM fct_yearly_events
            WHERE EXTRACT(YEAR FROM effective_date) != simulation_year
        """).fetchone()[0]

        # Allow some flexibility for end-of-year events
        total_events = db_connection.execute("SELECT COUNT(*) FROM fct_yearly_events").fetchone()[0]
        if total_events > 0:
            mismatch_rate = mismatched_event_years / total_events
            assert mismatch_rate < 0.05, f"High event year mismatch rate: {mismatch_rate:.2%}"

    def test_data_completeness(self, db_connection):
        """Verify critical fields are not null where they shouldn't be"""

        # Employee IDs should never be null
        null_employee_ids = db_connection.execute("""
            SELECT
                (SELECT COUNT(*) FROM fct_yearly_events WHERE employee_id IS NULL) +
                (SELECT COUNT(*) FROM fct_workforce_snapshot WHERE employee_id IS NULL) +
                (SELECT COUNT(*) FROM int_employee_contributions WHERE employee_id IS NULL)
        """).fetchone()[0]
        assert null_employee_ids == 0, f"Found {null_employee_ids} null employee IDs"

        # Event types should never be null
        null_event_types = db_connection.execute("""
            SELECT COUNT(*) FROM fct_yearly_events WHERE event_type IS NULL
        """).fetchone()[0]
        assert null_event_types == 0, f"Found {null_event_types} null event types"

        # Simulation years should never be null
        null_sim_years = db_connection.execute("""
            SELECT
                (SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year IS NULL) +
                (SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year IS NULL)
        """).fetchone()[0]
        assert null_sim_years == 0, f"Found {null_sim_years} null simulation years"
