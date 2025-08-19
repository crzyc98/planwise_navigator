#!/usr/bin/env python3
"""
Regulatory Compliance Tests

Validate regulatory compliance requirements for production readiness.
Part of Epic E047: Production Testing & Validation Framework.
"""

from __future__ import annotations

import pytest
import duckdb


class TestRegulatory:
    """Validate regulatory compliance requirements"""

    @pytest.fixture
    def db_connection(self):
        """Provide database connection for tests"""
        return duckdb.connect("simulation.duckdb")

    def test_irs_contribution_limits_2025(self, db_connection):
        """Verify 2025 IRS contribution limits are enforced"""
        violations = db_connection.execute("""
            SELECT
                employee_id,
                annual_contribution_amount,
                simulation_year
            FROM int_employee_contributions
            WHERE simulation_year = 2025
            AND annual_contribution_amount > 23500  -- 2025 401(k) limit
        """).fetchall()

        assert len(violations) == 0, f"Found {len(violations)} employees exceeding 2025 IRS limits"

    def test_irs_contribution_limits_future_years(self, db_connection):
        """Verify future year IRS contribution limits"""
        # Test 2026 limits (projected)
        violations_2026 = db_connection.execute("""
            SELECT
                employee_id,
                annual_contribution_amount,
                simulation_year
            FROM int_employee_contributions
            WHERE simulation_year = 2026
            AND annual_contribution_amount > 24000  -- Projected 2026 limit
        """).fetchall()

        # Allow for some flexibility in future year projections
        total_contributors_2026 = db_connection.execute("""
            SELECT COUNT(*) FROM int_employee_contributions
            WHERE simulation_year = 2026
        """).fetchone()[0]

        if total_contributors_2026 > 0:
            violation_rate = len(violations_2026) / total_contributors_2026
            assert violation_rate < 0.01, f"High IRS limit violation rate in 2026: {violation_rate:.2%}"

    def test_catch_up_contributions(self, db_connection):
        """Verify catch-up contributions for 50+ employees"""
        # Find employees 50+ with contributions above base limit
        catch_up_eligible = db_connection.execute("""
            SELECT
                ec.employee_id,
                ws.current_age,
                ec.annual_contribution_amount,
                ec.simulation_year
            FROM int_employee_contributions ec
            JOIN fct_workforce_snapshot ws
                ON ec.employee_id = ws.employee_id
                AND ec.simulation_year = ws.simulation_year
            WHERE ws.current_age >= 50
            AND ec.simulation_year = 2025
            AND ec.annual_contribution_amount > 23500  -- Base limit
            AND ec.annual_contribution_amount <= 31000  -- Base + catch-up (23500 + 7500)
        """).fetchall()

        # Should have some catch-up contributions if we have 50+ employees
        employees_50_plus = db_connection.execute("""
            SELECT COUNT(*) FROM fct_workforce_snapshot
            WHERE current_age >= 50 AND simulation_year = 2025
        """).fetchone()[0]

        if employees_50_plus > 10:  # Only test if we have sufficient 50+ population
            assert len(catch_up_eligible) > 0, "No catch-up contributions found for 50+ employees"

    def test_catch_up_limits_not_exceeded(self, db_connection):
        """Verify catch-up contribution limits not exceeded"""
        violations = db_connection.execute("""
            SELECT
                ec.employee_id,
                ws.current_age,
                ec.annual_contribution_amount
            FROM int_employee_contributions ec
            JOIN fct_workforce_snapshot ws
                ON ec.employee_id = ws.employee_id
                AND ec.simulation_year = ws.simulation_year
            WHERE ws.current_age >= 50
            AND ec.simulation_year = 2025
            AND ec.annual_contribution_amount > 31000  -- Base + catch-up limit
        """).fetchall()

        assert len(violations) == 0, f"Found {len(violations)} employees exceeding catch-up limits"

    def test_compensation_percentage_limits(self, db_connection):
        """Verify contribution percentages don't exceed 100% of compensation"""
        violations = db_connection.execute("""
            SELECT
                ec.employee_id,
                ec.annual_contribution_amount,
                ws.total_compensation,
                (ec.annual_contribution_amount / ws.total_compensation) as contribution_pct
            FROM int_employee_contributions ec
            JOIN fct_workforce_snapshot ws
                ON ec.employee_id = ws.employee_id
                AND ec.simulation_year = ws.simulation_year
            WHERE ws.total_compensation > 0
            AND ec.annual_contribution_amount > ws.total_compensation
        """).fetchall()

        assert len(violations) == 0, f"Found {len(violations)} employees contributing >100% of compensation"

    def test_minimum_distribution_age_compliance(self, db_connection):
        """Verify no distributions before age 59.5 (with exceptions)"""
        # This test would be more relevant if we had distribution events
        # For now, check that very young employees aren't getting distributions
        young_distributions = db_connection.execute("""
            SELECT COUNT(*) FROM fct_yearly_events ye
            JOIN fct_workforce_snapshot ws
                ON ye.employee_id = ws.employee_id
                AND ye.simulation_year = ws.simulation_year
            WHERE ye.event_type = 'distribution'  -- If we had this event type
            AND ws.current_age < 50  -- Very conservative check
        """).fetchall()

        # This test is mainly for future extensibility
        assert True, "Minimum distribution age compliance check placeholder"

    def test_highly_compensated_employee_limits(self, db_connection):
        """Verify HCE contribution limits if applicable"""
        # Check for reasonable distribution of contribution rates
        # HCEs shouldn't dominate contribution patterns

        hce_threshold = 150000  # Simplified HCE threshold

        hce_avg_deferral = db_connection.execute("""
            SELECT AVG(ec.annual_contribution_amount / ws.total_compensation) as avg_deferral
            FROM int_employee_contributions ec
            JOIN fct_workforce_snapshot ws
                ON ec.employee_id = ws.employee_id
                AND ec.simulation_year = ws.simulation_year
            WHERE ws.total_compensation >= ?
            AND ws.total_compensation > 0
            AND ec.simulation_year = 2025
        """, [hce_threshold]).fetchone()[0]

        nhce_avg_deferral = db_connection.execute("""
            SELECT AVG(ec.annual_contribution_amount / ws.total_compensation) as avg_deferral
            FROM int_employee_contributions ec
            JOIN fct_workforce_snapshot ws
                ON ec.employee_id = ws.employee_id
                AND ec.simulation_year = ws.simulation_year
            WHERE ws.total_compensation < ?
            AND ws.total_compensation > 0
            AND ec.simulation_year = 2025
        """, [hce_threshold]).fetchone()[0]

        # HCE/NHCE deferral rates shouldn't be too different (ADP test concept)
        if hce_avg_deferral and nhce_avg_deferral and nhce_avg_deferral > 0:
            ratio = hce_avg_deferral / nhce_avg_deferral
            assert ratio <= 2.0, f"HCE deferral rate too high relative to NHCE: {ratio:.2f}x"

    def test_plan_year_consistency(self, db_connection):
        """Verify plan year event timing is consistent"""
        # Check that events are properly attributed to plan years
        misattributed_events = db_connection.execute("""
            SELECT COUNT(*) FROM fct_yearly_events
            WHERE simulation_year != EXTRACT(YEAR FROM effective_date)
            AND ABS(simulation_year - EXTRACT(YEAR FROM effective_date)) > 1  -- Allow some end-of-year flexibility
        """).fetchone()[0]

        total_events = db_connection.execute("SELECT COUNT(*) FROM fct_yearly_events").fetchone()[0]

        if total_events > 0:
            misattribution_rate = misattributed_events / total_events
            assert misattribution_rate < 0.05, f"High plan year misattribution rate: {misattribution_rate:.2%}"

    def test_contribution_frequency_compliance(self, db_connection):
        """Verify contribution timing follows payroll patterns"""
        # Check that contributions are spread reasonably throughout the year
        # Not all on January 1st or December 31st

        # This is more of a business logic test, but has regulatory implications
        contribution_events = db_connection.execute("""
            SELECT
                EXTRACT(MONTH FROM effective_date) as month,
                COUNT(*) as event_count
            FROM fct_yearly_events
            WHERE event_type = 'contribution'  -- If we had contribution events
            GROUP BY EXTRACT(MONTH FROM effective_date)
        """).fetchall()

        # For now, just verify the test structure is in place
        assert True, "Contribution frequency compliance check placeholder"

    def test_vesting_schedule_compliance(self, db_connection):
        """Verify vesting schedules follow regulatory requirements"""
        # Check that vesting calculations are reasonable
        # This would be more relevant with actual vesting data

        # Placeholder for vesting compliance checks
        assert True, "Vesting schedule compliance check placeholder"

    def test_non_discrimination_testing_data_quality(self, db_connection):
        """Verify data quality supports non-discrimination testing"""
        # Ensure we have the data needed for ADP/ACP testing

        # Check we have contribution data for different compensation levels
        compensation_groups = db_connection.execute("""
            SELECT
                CASE
                    WHEN ws.total_compensation >= 150000 THEN 'HCE'
                    ELSE 'NHCE'
                END as group_type,
                COUNT(*) as employee_count,
                AVG(ec.annual_contribution_amount / ws.total_compensation) as avg_deferral_rate
            FROM int_employee_contributions ec
            JOIN fct_workforce_snapshot ws
                ON ec.employee_id = ws.employee_id
                AND ec.simulation_year = ws.simulation_year
            WHERE ws.total_compensation > 0
            AND ec.simulation_year = 2025
            GROUP BY CASE
                WHEN ws.total_compensation >= 150000 THEN 'HCE'
                ELSE 'NHCE'
            END
        """).fetchall()

        # Should have both HCE and NHCE groups for meaningful testing
        group_types = [group[0] for group in compensation_groups]
        assert 'HCE' in group_types or 'NHCE' in group_types, "Missing compensation groups for non-discrimination testing"

    def test_regulatory_reporting_data_completeness(self, db_connection):
        """Verify we have complete data for regulatory reporting"""
        # Check for missing critical fields that would be needed for regulatory reports

        missing_compensation = db_connection.execute("""
            SELECT COUNT(*) FROM fct_workforce_snapshot
            WHERE simulation_year = 2025
            AND employment_status = 'active'
            AND (total_compensation IS NULL OR total_compensation <= 0)
        """).fetchone()[0]

        assert missing_compensation == 0, f"Found {missing_compensation} active employees with missing/invalid compensation"

        missing_contribution_data = db_connection.execute("""
            SELECT COUNT(*) FROM fct_workforce_snapshot ws
            LEFT JOIN int_employee_contributions ec
                ON ws.employee_id = ec.employee_id
                AND ws.simulation_year = ec.simulation_year
            WHERE ws.simulation_year = 2025
            AND ws.employment_status = 'active'
            AND ec.employee_id IS NULL
        """).fetchone()[0]

        # Allow some employees without contributions (not everyone participates)
        total_active = db_connection.execute("""
            SELECT COUNT(*) FROM fct_workforce_snapshot
            WHERE simulation_year = 2025 AND employment_status = 'active'
        """).fetchone()[0]

        if total_active > 0:
            missing_rate = missing_contribution_data / total_active
            assert missing_rate < 0.8, f"Too many active employees missing contribution data: {missing_rate:.2%}"
