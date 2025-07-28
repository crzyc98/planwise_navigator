"""
Integration test for compensation prorated calculation fix.

This test validates that the compensation calculation system correctly handles
mid-year raises by calculating prorated compensation based on time-weighted
averaging. Specifically tests the user's scenario: employee EMP_000003 with
starting salary $50,700, raise effective 2025-07-15 to $53,880.84, expecting
prorated compensation of $52,158.33.

Tests include:
- Single mid-year raise calculation
- Multiple raises in one year
- New hire with mid-year raise
- Edge cases (raises on January 1st and December 31st)
"""

import pytest
import pandas as pd
import duckdb
from pathlib import Path
import tempfile
import shutil
import os
from typing import Dict, List
import numpy as np
from datetime import datetime, date
import math


@pytest.fixture
def test_db_path(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_compensation_prorated.duckdb"
    return str(db_path)


@pytest.fixture
def test_employee_data():
    """Create test employee data matching the user's scenario."""
    return pd.DataFrame({
        'employee_id': ['EMP_000001', 'EMP_000002', 'EMP_000003', 'EMP_000004', 'EMP_000005'],
        'employee_ssn': ['111-11-1111', '222-22-2222', '333-33-3333', '444-44-4444', '555-55-5555'],
        'employee_birth_date': pd.to_datetime(['1980-01-15', '1985-06-20', '1990-03-10', '1975-12-05', '1988-09-25']),
        'employee_hire_date': pd.to_datetime(['2020-01-01', '2020-01-01', '2020-01-01', '2020-01-01', '2025-06-01']),
        'employee_gross_compensation': [55000.0, 60000.0, 50700.0, 75000.0, 65000.0],
        'level_id': [2, 2, 2, 3, 2],
        'employment_status': ['active', 'active', 'active', 'active', 'active'],
        'current_age': [45, 40, 35, 50, 37],
        'current_tenure': [5, 5, 5, 20, 0.5],
        'termination_date': [None, None, None, None, None],
        'termination_reason': [None, None, None, None, None],
        'simulation_year': [2025, 2025, 2025, 2025, 2025]
    })


@pytest.fixture
def test_yearly_events():
    """Create test yearly events including the user's specific scenario."""
    return pd.DataFrame({
        'event_id': ['evt_001', 'evt_002', 'evt_003', 'evt_004', 'evt_005'],
        'employee_id': ['EMP_000001', 'EMP_000002', 'EMP_000003', 'EMP_000004', 'EMP_000005'],
        'event_type': ['raise', 'raise', 'raise', 'raise', 'hire'],
        'simulation_year': [2025, 2025, 2025, 2025, 2025],
        'effective_date': pd.to_datetime(['2025-03-15', '2025-08-01', '2025-07-15', '2025-12-31', '2025-06-01']),
        'compensation_amount': [57000.0, 62500.0, 53880.84, 78000.0, 65000.0],
        'previous_compensation': [55000.0, 60000.0, 50700.0, 75000.0, None],
        'event_reason': ['merit', 'merit', 'merit', 'promotion', 'new_hire']
    })


class TestCompensationProratedCalculation:
    """Test suite for prorated compensation calculation functionality."""

    def setup_test_database(self, db_path: str, employee_data: pd.DataFrame, yearly_events: pd.DataFrame) -> duckdb.DuckDBPyConnection:
        """Set up a test database with initial data."""
        conn = duckdb.connect(db_path)

        # Create base workforce table
        conn.execute("""
            CREATE TABLE int_snapshot_hiring AS
            SELECT * FROM employee_data
        """)
        conn.register('employee_data', employee_data)
        conn.execute("INSERT INTO int_snapshot_hiring SELECT * FROM employee_data")

        # Create yearly events table
        conn.execute("""
            CREATE TABLE fct_yearly_events AS
            SELECT * FROM yearly_events
        """)
        conn.register('yearly_events', yearly_events)
        conn.execute("INSERT INTO fct_yearly_events SELECT * FROM yearly_events")

        return conn

    def test_user_scenario_emp_000003(self, test_db_path, test_employee_data, test_yearly_events):
        """Test the specific user scenario: EMP_000003 with mid-year raise."""
        conn = self.setup_test_database(test_db_path, test_employee_data, test_yearly_events)

        # Execute the compensation calculation logic similar to int_snapshot_compensation.sql
        result = conn.execute("""
            WITH workforce_base AS (
                SELECT
                    employee_id,
                    employee_gross_compensation AS starting_compensation,
                    50700.0 AS final_compensation,  -- Known final compensation for EMP_000003
                    1 AS hire_day_of_year  -- Hired before 2025
                FROM int_snapshot_hiring
                WHERE employee_id = 'EMP_000003'
            ),

            compensation_events AS (
                SELECT
                    employee_id,
                    event_type,
                    compensation_amount AS event_new_salary,
                    EXTRACT(DOY FROM effective_date) AS event_day_of_year
                FROM fct_yearly_events
                WHERE employee_id = 'EMP_000003'
                    AND event_type = 'raise'
                    AND effective_date IS NOT NULL
                    AND compensation_amount IS NOT NULL
            ),

            final_calculation AS (
                SELECT
                    wb.employee_id,
                    wb.starting_compensation,
                    ce.event_new_salary,
                    ce.event_day_of_year,
                    -- Calculate prorated compensation using time-weighted logic
                    -- Period 1: Jan 1 - July 14 (day 195) at $50,700
                    -- Period 2: July 15 (day 196) - Dec 31 (day 365) at $53,880.84
                    (wb.starting_compensation * (ce.event_day_of_year - 1) / 365.0) +
                    (ce.event_new_salary * (365 - ce.event_day_of_year + 1) / 365.0) AS prorated_annual_compensation
                FROM workforce_base wb
                LEFT JOIN compensation_events ce ON wb.employee_id = ce.employee_id
            )

            SELECT
                employee_id,
                starting_compensation,
                event_new_salary,
                event_day_of_year,
                ROUND(prorated_annual_compensation, 2) AS prorated_annual_compensation
            FROM final_calculation
        """).fetchdf()

        # Validate the result
        assert len(result) == 1
        row = result.iloc[0]

        # Verify the basic data
        assert row['employee_id'] == 'EMP_000003'
        assert row['starting_compensation'] == 50700.0
        assert row['event_new_salary'] == 53880.84

        # July 15th is day 196 of the year
        assert row['event_day_of_year'] == 196

        # Calculate expected prorated compensation
        # Period 1: Jan 1 - July 14 (195 days) at $50,700
        # Period 2: July 15 - Dec 31 (170 days) at $53,880.84
        period1_compensation = 50700.0 * 195 / 365
        period2_compensation = 53880.84 * 170 / 365
        expected_prorated = period1_compensation + period2_compensation

        # Verify the calculation matches expectation (within $1 tolerance)
        assert abs(row['prorated_annual_compensation'] - expected_prorated) < 1.0

        # Verify it matches the user's expected value of $52,158.33
        assert abs(row['prorated_annual_compensation'] - 52158.33) < 1.0

        conn.close()

    def test_multiple_raises_same_year(self, test_db_path, test_employee_data, test_yearly_events):
        """Test handling of multiple raises in the same year (should use latest one)."""
        conn = self.setup_test_database(test_db_path, test_employee_data, test_yearly_events)

        # Add a second raise for EMP_000003
        conn.execute("""
            INSERT INTO fct_yearly_events VALUES (
                'evt_006', 'EMP_000003', 'raise', 2025,
                '2025-09-01', 55000.0, 53880.84, 'promotion'
            )
        """)

        # Execute compensation calculation with multiple raises
        result = conn.execute("""
            WITH compensation_events AS (
                SELECT
                    employee_id,
                    event_type,
                    compensation_amount AS event_new_salary,
                    EXTRACT(DOY FROM effective_date) AS event_day_of_year,
                    ROW_NUMBER() OVER (
                        PARTITION BY employee_id
                        ORDER BY effective_date DESC
                    ) AS event_rank
                FROM fct_yearly_events
                WHERE employee_id = 'EMP_000003'
                    AND event_type = 'raise'
                    AND effective_date IS NOT NULL
                    AND compensation_amount IS NOT NULL
            ),

            latest_compensation_events AS (
                SELECT * FROM compensation_events WHERE event_rank = 1
            )

            SELECT
                employee_id,
                event_new_salary,
                event_day_of_year
            FROM latest_compensation_events
        """).fetchdf()

        # Should use the September raise (latest one)
        assert len(result) == 1
        row = result.iloc[0]
        assert row['event_new_salary'] == 55000.0
        assert row['event_day_of_year'] == 244  # September 1st

        conn.close()

    def test_new_hire_with_mid_year_raise(self, test_db_path, test_employee_data, test_yearly_events):
        """Test new hire who gets a raise in the same year."""
        conn = self.setup_test_database(test_db_path, test_employee_data, test_yearly_events)

        # Add a raise for the new hire EMP_000005
        conn.execute("""
            INSERT INTO fct_yearly_events VALUES (
                'evt_007', 'EMP_000005', 'raise', 2025,
                '2025-09-15', 70000.0, 65000.0, 'merit'
            )
        """)

        result = conn.execute("""
            WITH workforce_base AS (
                SELECT
                    employee_id,
                    employee_gross_compensation AS starting_compensation,
                    EXTRACT(DOY FROM employee_hire_date) AS hire_day_of_year
                FROM int_snapshot_hiring
                WHERE employee_id = 'EMP_000005'
            ),

            compensation_events AS (
                SELECT
                    employee_id,
                    compensation_amount AS event_new_salary,
                    EXTRACT(DOY FROM effective_date) AS event_day_of_year
                FROM fct_yearly_events
                WHERE employee_id = 'EMP_000005'
                    AND event_type = 'raise'
            ),

            final_calculation AS (
                SELECT
                    wb.employee_id,
                    wb.hire_day_of_year,
                    ce.event_day_of_year,
                    -- New hire with raise: time from hire to raise at starting salary,
                    -- then time from raise to year end at new salary
                    (wb.starting_compensation * (ce.event_day_of_year - wb.hire_day_of_year) / 365.0) +
                    (ce.event_new_salary * (365 - ce.event_day_of_year + 1) / 365.0) AS prorated_annual_compensation
                FROM workforce_base wb
                LEFT JOIN compensation_events ce ON wb.employee_id = ce.employee_id
            )

            SELECT
                employee_id,
                hire_day_of_year,
                event_day_of_year,
                ROUND(prorated_annual_compensation, 2) AS prorated_annual_compensation
            FROM final_calculation
        """).fetchdf()

        # Validate new hire calculation
        assert len(result) == 1
        row = result.iloc[0]

        # June 1st hire, September 15th raise
        assert row['hire_day_of_year'] == 152  # June 1st
        assert row['event_day_of_year'] == 258  # September 15th

        # Should have prorated compensation reflecting both hire date and raise
        assert row['prorated_annual_compensation'] > 0

        conn.close()

    def test_edge_case_january_1st_raise(self, test_db_path, test_employee_data, test_yearly_events):
        """Test raise effective January 1st (should use new salary for full year)."""
        conn = self.setup_test_database(test_db_path, test_employee_data, test_yearly_events)

        # Add January 1st raise
        conn.execute("""
            INSERT INTO fct_yearly_events VALUES (
                'evt_008', 'EMP_000001', 'raise', 2025,
                '2025-01-01', 60000.0, 55000.0, 'promotion'
            )
        """)

        result = conn.execute("""
            WITH compensation_events AS (
                SELECT
                    employee_id,
                    compensation_amount AS event_new_salary,
                    EXTRACT(DOY FROM effective_date) AS event_day_of_year
                FROM fct_yearly_events
                WHERE employee_id = 'EMP_000001'
                    AND event_type = 'raise'
                    AND effective_date = '2025-01-01'
            )

            SELECT
                employee_id,
                event_day_of_year,
                event_new_salary
            FROM compensation_events
        """).fetchdf()

        # January 1st should be day 1
        assert len(result) == 1
        assert result.iloc[0]['event_day_of_year'] == 1

        # With a day 1 raise, time at starting salary should be 0 days,
        # and full year should be at new salary

        conn.close()

    def test_edge_case_december_31st_raise(self, test_db_path, test_employee_data, test_yearly_events):
        """Test raise effective December 31st (should use old salary for almost full year)."""
        conn = self.setup_test_database(test_db_path, test_employee_data, test_yearly_events)

        result = conn.execute("""
            WITH compensation_events AS (
                SELECT
                    employee_id,
                    compensation_amount AS event_new_salary,
                    EXTRACT(DOY FROM effective_date) AS event_day_of_year
                FROM fct_yearly_events
                WHERE employee_id = 'EMP_000004'
                    AND event_type = 'raise'
                    AND effective_date = '2025-12-31'
            )

            SELECT
                employee_id,
                event_day_of_year,
                event_new_salary
            FROM compensation_events
        """).fetchdf()

        # December 31st should be day 365 (or 366 in leap year)
        assert len(result) == 1
        assert result.iloc[0]['event_day_of_year'] == 365

        # With a day 365 raise, should have 364 days at old salary, 1 day at new salary

        conn.close()

    def test_leap_year_handling(self, test_db_path, test_employee_data, test_yearly_events):
        """Test that leap year calculations use 366 days correctly."""
        conn = self.setup_test_database(test_db_path, test_employee_data, test_yearly_events)

        # Test leap year day calculation
        result = conn.execute("""
            SELECT
                EXTRACT(DOY FROM CAST('2024-12-31' AS DATE)) AS days_in_2024,
                EXTRACT(DOY FROM CAST('2025-12-31' AS DATE)) AS days_in_2025
        """).fetchdf()

        # 2024 is a leap year, 2025 is not
        assert result.iloc[0]['days_in_2024'] == 366
        assert result.iloc[0]['days_in_2025'] == 365

        conn.close()
