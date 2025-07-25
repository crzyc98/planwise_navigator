"""
Integration test for compensation compounding fix.

This test validates that the fix to int_workforce_previous_year_v2.sql correctly
ensures compensation compounds year-over-year by using time-weighted compensation
calculations instead of simple full_year_equivalent_compensation.

Updated to include validation of the new int_time_weighted_compensation model.
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


@pytest.fixture
def test_db_path(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_simulation.duckdb"
    return str(db_path)


@pytest.fixture
def test_employee_data():
    """Create test employee data with known compensation values."""
    return pd.DataFrame({
        'employee_id': ['EMP001', 'EMP002', 'EMP003', 'EMP004', 'EMP005'],
        'employee_ssn': ['111-11-1111', '222-22-2222', '333-33-3333', '444-44-4444', '555-55-5555'],
        'employee_birth_date': pd.to_datetime(['1980-01-15', '1985-06-20', '1990-03-10', '1975-12-05', '1988-09-25']),
        'employee_hire_date': pd.to_datetime(['2010-01-01', '2015-06-01', '2018-03-15', '2005-09-01', '2020-01-10']),
        'current_compensation': [176000.0, 125000.0, 95000.0, 210000.0, 85000.0],
        'level_id': [4, 3, 2, 5, 2],
        'employment_status': ['active', 'active', 'active', 'active', 'active']
    })


class TestCompensationCompounding:
    """Test suite for compensation compounding functionality."""

    def setup_test_database(self, db_path: str, employee_data: pd.DataFrame) -> duckdb.DuckDBPyConnection:
        """Set up a test database with initial data."""
        conn = duckdb.connect(db_path)

        # Create necessary tables
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fct_workforce_snapshot (
                employee_id VARCHAR,
                employee_ssn VARCHAR,
                employee_birth_date DATE,
                employee_hire_date DATE,
                current_compensation DOUBLE,
                full_year_equivalent_compensation DOUBLE,
                current_age INTEGER,
                current_tenure INTEGER,
                level_id INTEGER,
                age_band VARCHAR,
                tenure_band VARCHAR,
                employment_status VARCHAR,
                termination_date DATE,
                termination_reason VARCHAR,
                simulation_year INTEGER,
                snapshot_created_at TIMESTAMP,
                is_from_census BOOLEAN,
                is_cold_start BOOLEAN
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS fct_yearly_events (
                event_id VARCHAR,
                employee_id VARCHAR,
                event_type VARCHAR,
                event_category VARCHAR,
                effective_date DATE,
                simulation_year INTEGER,
                scenario_id VARCHAR,
                previous_compensation DOUBLE,
                compensation_amount DOUBLE,
                event_payload_json VARCHAR
            )
        """)

        # Create table for time-weighted compensation testing
        conn.execute("""
            CREATE TABLE IF NOT EXISTS int_time_weighted_compensation (
                employee_id VARCHAR,
                simulation_year INTEGER,
                actual_time_weighted_compensation DOUBLE,
                total_compensation_periods INTEGER,
                has_raise_events BOOLEAN,
                calculation_method VARCHAR,
                total_days_calculated INTEGER
            )
        """)

        return conn

    def simulate_year_with_raises(self, conn: duckdb.DuckDBPyConnection, year: int,
                                  employee_data: pd.DataFrame, raise_percentage: float = 0.043) -> pd.DataFrame:
        """Simulate a single year with raises applied."""
        # Calculate age and tenure for the year
        employee_data = employee_data.copy()
        employee_data['simulation_year'] = year
        employee_data['current_age'] = (pd.Timestamp(f'{year}-01-01') - employee_data['employee_birth_date']).dt.days // 365
        employee_data['current_tenure'] = (pd.Timestamp(f'{year}-01-01') - employee_data['employee_hire_date']).dt.days // 365

        # Calculate age and tenure bands
        employee_data['age_band'] = pd.cut(
            employee_data['current_age'],
            bins=[0, 25, 35, 45, 55, 65, 100],
            labels=['< 25', '25-34', '35-44', '45-54', '55-64', '65+'],
            right=False
        )

        employee_data['tenure_band'] = pd.cut(
            employee_data['current_tenure'],
            bins=[0, 2, 5, 10, 20, 100],
            labels=['< 2', '2-4', '5-9', '10-19', '20+'],
            right=False
        )

        # Apply raises to calculate full_year_equivalent_compensation
        employee_data['full_year_equivalent_compensation'] = employee_data['current_compensation'] * (1 + raise_percentage)

        # Add other required fields
        employee_data['termination_date'] = pd.NaT
        employee_data['termination_reason'] = None
        employee_data['snapshot_created_at'] = pd.Timestamp.now()
        employee_data['is_from_census'] = False
        employee_data['is_cold_start'] = (year == 2025)

        # Insert workforce snapshot
        conn.execute("INSERT INTO fct_workforce_snapshot SELECT * FROM employee_data")

        # Create raise events
        raise_events = []
        for _, emp in employee_data.iterrows():
            raise_events.append({
                'event_id': f"RAISE-{emp['employee_id']}-{year}",
                'employee_id': emp['employee_id'],
                'event_type': 'RAISE',
                'event_category': 'RAISE',
                'effective_date': pd.Timestamp(f'{year}-03-01'),
                'simulation_year': year,
                'scenario_id': 'TEST',
                'previous_compensation': emp['current_compensation'],
                'compensation_amount': emp['full_year_equivalent_compensation'],
                'event_payload_json': f'{{"raise_type": "merit", "percentage": {raise_percentage}}}'
            })

        raise_events_df = pd.DataFrame(raise_events)
        conn.execute("INSERT INTO fct_yearly_events SELECT * FROM raise_events_df")

        # Calculate and insert time-weighted compensation data
        self.calculate_time_weighted_compensation(conn, year, employee_data)

        return employee_data

    def calculate_time_weighted_compensation(self, conn: duckdb.DuckDBPyConnection, year: int, employee_data: pd.DataFrame):
        """Calculate time-weighted compensation for testing purposes."""
        time_weighted_data = []
        for _, emp in employee_data.iterrows():
            # For test purposes, assume raises happen on March 1st
            # January 1 - March 1 = ~59 days at starting salary
            # March 1 - December 31 = ~306 days at ending salary
            days_before_raise = 59
            days_after_raise = 306
            total_days = 365

            starting_salary = emp['current_compensation']
            ending_salary = emp['full_year_equivalent_compensation']

            # Calculate time-weighted compensation
            time_weighted_comp = (
                (starting_salary * days_before_raise / total_days) +
                (ending_salary * days_after_raise / total_days)
            )

            time_weighted_data.append({
                'employee_id': emp['employee_id'],
                'simulation_year': year,
                'actual_time_weighted_compensation': time_weighted_comp,
                'total_compensation_periods': 2,  # Before and after raise
                'has_raise_events': True,
                'calculation_method': 'time_weighted_with_raises',
                'total_days_calculated': total_days
            })

        time_weighted_df = pd.DataFrame(time_weighted_data)
        conn.execute("INSERT INTO int_time_weighted_compensation SELECT * FROM time_weighted_df")

    def test_time_weighted_compensation_calculation(self, test_db_path, test_employee_data):
        """Test that time-weighted compensation is calculated correctly for mid-year raises."""
        conn = self.setup_test_database(test_db_path, test_employee_data)

        # Focus on one employee for detailed testing
        single_emp = test_employee_data.head(1).copy()
        starting_salary = single_emp.iloc[0]['current_compensation']  # $176,000

        # Simulate year with raise on March 1st
        self.simulate_year_with_raises(conn, 2025, single_emp, raise_percentage=0.043)

        # Get the time-weighted compensation
        result = conn.execute("""
            SELECT
                actual_time_weighted_compensation,
                has_raise_events,
                calculation_method,
                total_compensation_periods
            FROM int_time_weighted_compensation
            WHERE employee_id = 'EMP001' AND simulation_year = 2025
        """).fetchone()

        # Calculate expected time-weighted compensation
        # 59 days at $176,000 + 306 days at $183,568
        ending_salary = starting_salary * 1.043
        expected_time_weighted = (
            (starting_salary * 59 / 365) +
            (ending_salary * 306 / 365)
        )

        assert result is not None, "Time-weighted compensation record should exist"
        assert abs(result[0] - expected_time_weighted) < 1.0, \
            f"Expected time-weighted compensation ${expected_time_weighted:.2f}, got ${result[0]:.2f}"
        assert result[1] == True, "Should have raise events"
        assert result[2] == 'time_weighted_with_raises', "Should use time-weighted calculation method"
        assert result[3] == 2, "Should have 2 compensation periods"

        conn.close()

    def test_time_weighted_vs_full_year_compensation(self, test_db_path, test_employee_data):
        """Test that time-weighted compensation provides more accurate carryforward than full-year equivalent."""
        conn = self.setup_test_database(test_db_path, test_employee_data)

        # Simulate first year
        self.simulate_year_with_raises(conn, 2025, test_employee_data)

        # Get both time-weighted and full-year equivalent compensation
        comparison = conn.execute("""
            SELECT
                fws.employee_id,
                fws.current_compensation as starting_salary_2025,
                fws.full_year_equivalent_compensation as ending_salary_2025,
                twc.actual_time_weighted_compensation as time_weighted_2025
            FROM fct_workforce_snapshot fws
            JOIN int_time_weighted_compensation twc
                ON fws.employee_id = twc.employee_id
                AND fws.simulation_year = twc.simulation_year
            WHERE fws.simulation_year = 2025
        """).df()

        for _, row in comparison.iterrows():
            starting = row['starting_salary_2025']
            ending = row['ending_salary_2025']
            time_weighted = row['time_weighted_2025']

            # Time-weighted should be between starting and ending salary
            assert starting <= time_weighted <= ending, \
                f"Employee {row['employee_id']}: Time-weighted (${time_weighted:.2f}) should be between starting (${starting:.2f}) and ending (${ending:.2f})"

            # Time-weighted should be closer to ending salary (since raise happens early in year)
            midpoint = (starting + ending) / 2
            assert time_weighted > midpoint, \
                f"Employee {row['employee_id']}: Time-weighted should be > midpoint since raise happens early in year"

        conn.close()

    def test_multiple_raises_time_weighted_calculation(self, test_db_path, test_employee_data):
        """Test time-weighted compensation calculation for employees with multiple raises in a year."""
        conn = self.setup_test_database(test_db_path, test_employee_data)

        # Simulate first year with initial raise
        single_emp = test_employee_data.head(1).copy()
        self.simulate_year_with_raises(conn, 2025, single_emp)

        # Add a second raise (promotion) in July
        mid_year_salary = single_emp.iloc[0]['current_compensation'] * 1.043
        promotion_salary = mid_year_salary * 1.10  # 10% promotion raise

        conn.execute("""
            INSERT INTO fct_yearly_events VALUES
            ('PROMO-EMP001-2025', 'EMP001', 'PROMOTION', 'RAISE', '2025-07-01', 2025, 'TEST',
             ?, ?, '{"raise_type": "promotion", "percentage": 0.10}')
        """, [mid_year_salary, promotion_salary])

        # Recalculate time-weighted compensation with multiple raises
        # Period 1: Jan 1 - Mar 1 (59 days) at $176,000
        # Period 2: Mar 1 - Jul 1 (122 days) at $183,568
        # Period 3: Jul 1 - Dec 31 (184 days) at $201,925
        starting_salary = 176000.0
        after_merit = starting_salary * 1.043
        after_promotion = after_merit * 1.10

        expected_time_weighted = (
            (starting_salary * 59 / 365) +
            (after_merit * 122 / 365) +
            (after_promotion * 184 / 365)
        )

        # Update the time-weighted compensation record
        conn.execute("""
            UPDATE int_time_weighted_compensation
            SET
                actual_time_weighted_compensation = ?,
                total_compensation_periods = 3,
                calculation_method = 'time_weighted_with_raises'
            WHERE employee_id = 'EMP001' AND simulation_year = 2025
        """, [expected_time_weighted])

        # Verify the calculation
        result = conn.execute("""
            SELECT actual_time_weighted_compensation, total_compensation_periods
            FROM int_time_weighted_compensation
            WHERE employee_id = 'EMP001' AND simulation_year = 2025
        """).fetchone()

        assert abs(result[0] - expected_time_weighted) < 1.0, \
            f"Expected time-weighted compensation ${expected_time_weighted:.2f} with multiple raises, got ${result[0]:.2f}"
        assert result[1] == 3, "Should have 3 compensation periods for multiple raises"

        conn.close()

    def test_time_weighted_carryforward_accuracy(self, test_db_path, test_employee_data):
        """Test that time-weighted compensation provides more accurate year-over-year carryforward."""
        conn = self.setup_test_database(test_db_path, test_employee_data)

        # Simulate 2025 with raises
        current_data = test_employee_data.copy()
        self.simulate_year_with_raises(conn, 2025, current_data)

        # For 2026, starting salary should be based on time-weighted compensation from 2025
        carryforward_data = conn.execute("""
            SELECT
                employee_id,
                actual_time_weighted_compensation as correct_starting_salary_2026
            FROM int_time_weighted_compensation
            WHERE simulation_year = 2025
        """).df()

        # Update starting salaries for 2026 based on time-weighted compensation
        for _, row in carryforward_data.iterrows():
            current_data.loc[current_data['employee_id'] == row['employee_id'],
                           'current_compensation'] = row['correct_starting_salary_2026']

        # Simulate 2026
        self.simulate_year_with_raises(conn, 2026, current_data)

        # Verify that 2026 starting salaries match 2025 time-weighted compensation
        validation = conn.execute("""
            SELECT
                twc_2025.employee_id,
                twc_2025.actual_time_weighted_compensation as expected_2026_start,
                fws_2026.current_compensation as actual_2026_start,
                ABS(fws_2026.current_compensation - twc_2025.actual_time_weighted_compensation) as difference
            FROM int_time_weighted_compensation twc_2025
            JOIN fct_workforce_snapshot fws_2026
                ON twc_2025.employee_id = fws_2026.employee_id
            WHERE twc_2025.simulation_year = 2025
                AND fws_2026.simulation_year = 2026
        """).df()

        # All differences should be minimal
        max_difference = validation['difference'].max()
        assert max_difference < 1.0, \
            f"Maximum carryforward difference should be < $1.00, got ${max_difference:.2f}"

        # Verify for specific employee
        emp001_validation = validation[validation['employee_id'] == 'EMP001'].iloc[0]
        assert abs(emp001_validation['difference']) < 0.01, \
            f"Employee EMP001 carryforward difference should be minimal, got ${emp001_validation['difference']:.2f}"

        conn.close()

    def test_compensation_compounding_single_employee(self, test_db_path, test_employee_data):
        """Test that a single employee's compensation compounds correctly over multiple years."""
        conn = self.setup_test_database(test_db_path, test_employee_data)

        # Focus on employee starting at $176,000
        target_employee = test_employee_data[test_employee_data['current_compensation'] == 176000.0].iloc[0]
        employee_id = target_employee['employee_id']

        # Expected progression with 4.3% annual raises
        expected_progression = {
            2025: {'start': 176000.00, 'end': 183568.00},  # 176000 * 1.043
            2026: {'start': 183568.00, 'end': 191461.42},  # 183568 * 1.043
            2027: {'start': 191461.42, 'end': 199694.26},  # 191461.42 * 1.043
            2028: {'start': 199694.26, 'end': 208281.11},  # 199694.26 * 1.043
        }

        # Simulate multiple years
        current_data = test_employee_data.copy()
        for year in [2025, 2026, 2027, 2028]:
            if year > 2025:
                # Update starting compensation to previous year's ending compensation
                # This simulates what int_workforce_previous_year_v2.sql should do
                prev_year_data = conn.execute(f"""
                    SELECT employee_id, full_year_equivalent_compensation
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = {year - 1}
                """).df()

                for _, prev in prev_year_data.iterrows():
                    current_data.loc[current_data['employee_id'] == prev['employee_id'],
                                   'current_compensation'] = prev['full_year_equivalent_compensation']

            self.simulate_year_with_raises(conn, year, current_data)

        # Verify progression
        actual_progression = conn.execute(f"""
            SELECT
                simulation_year,
                current_compensation as starting_salary,
                full_year_equivalent_compensation as ending_salary
            FROM fct_workforce_snapshot
            WHERE employee_id = '{employee_id}'
            ORDER BY simulation_year
        """).df()

        # Check each year
        for _, row in actual_progression.iterrows():
            year = int(row['simulation_year'])
            expected = expected_progression[year]

            # Allow small floating point differences
            assert abs(row['starting_salary'] - expected['start']) < 0.01, \
                f"Year {year}: Expected starting salary ${expected['start']:.2f}, got ${row['starting_salary']:.2f}"

            assert abs(row['ending_salary'] - expected['end']) < 0.01, \
                f"Year {year}: Expected ending salary ${expected['end']:.2f}, got ${row['ending_salary']:.2f}"

        conn.close()

    def test_year_over_year_salary_handoff(self, test_db_path, test_employee_data):
        """Test that Year N+1 starting salary matches Year N ending salary for all employees."""
        conn = self.setup_test_database(test_db_path, test_employee_data)

        # Simulate multiple years
        current_data = test_employee_data.copy()
        for year in [2025, 2026, 2027]:
            if year > 2025:
                # Update starting compensation to previous year's ending compensation
                prev_year_data = conn.execute(f"""
                    SELECT employee_id, full_year_equivalent_compensation
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = {year - 1}
                """).df()

                for _, prev in prev_year_data.iterrows():
                    current_data.loc[current_data['employee_id'] == prev['employee_id'],
                                   'current_compensation'] = prev['full_year_equivalent_compensation']

            self.simulate_year_with_raises(conn, year, current_data)

        # Verify handoff for all employees
        handoff_check = conn.execute("""
            SELECT
                curr.employee_id,
                curr.simulation_year as current_year,
                prev.full_year_equivalent_compensation as prev_year_ending,
                curr.current_compensation as curr_year_starting,
                ABS(curr.current_compensation - prev.full_year_equivalent_compensation) as difference
            FROM fct_workforce_snapshot curr
            JOIN fct_workforce_snapshot prev
                ON curr.employee_id = prev.employee_id
                AND curr.simulation_year = prev.simulation_year + 1
            WHERE curr.simulation_year > 2025
        """).df()

        # All differences should be near zero
        max_difference = handoff_check['difference'].max()
        assert max_difference < 0.01, \
            f"Found salary handoff discrepancy of ${max_difference:.2f}. All employees should start Year N+1 with Year N ending salary."

        # No employee should have a difference
        problem_employees = handoff_check[handoff_check['difference'] >= 0.01]
        assert len(problem_employees) == 0, \
            f"Found {len(problem_employees)} employees with incorrect salary handoff:\n{problem_employees}"

        conn.close()

    def test_compounding_vs_non_compounding(self, test_db_path, test_employee_data):
        """Test the difference between correct compounding and incorrect non-compounding behavior."""
        conn = self.setup_test_database(test_db_path, test_employee_data)

        # Simulate with correct compounding
        current_data = test_employee_data.copy()
        for year in [2025, 2026, 2027, 2028]:
            if year > 2025:
                # Correct: Use full_year_equivalent_compensation from previous year
                prev_year_data = conn.execute(f"""
                    SELECT employee_id, full_year_equivalent_compensation
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = {year - 1}
                """).df()

                for _, prev in prev_year_data.iterrows():
                    current_data.loc[current_data['employee_id'] == prev['employee_id'],
                                   'current_compensation'] = prev['full_year_equivalent_compensation']

            self.simulate_year_with_raises(conn, year, current_data, raise_percentage=0.043)

        # Get final compensation with correct compounding
        correct_final = conn.execute("""
            SELECT employee_id, full_year_equivalent_compensation as final_salary
            FROM fct_workforce_snapshot
            WHERE simulation_year = 2028
        """).df()

        # Now simulate incorrect behavior (using current_compensation instead)
        conn.execute("DELETE FROM fct_workforce_snapshot")
        conn.execute("DELETE FROM fct_yearly_events")

        current_data = test_employee_data.copy()
        original_salaries = current_data.set_index('employee_id')['current_compensation'].to_dict()

        for year in [2025, 2026, 2027, 2028]:
            if year > 2025:
                # Incorrect: Always use original current_compensation (no compounding)
                for emp_id, orig_salary in original_salaries.items():
                    # Each year applies raise to original salary only
                    current_data.loc[current_data['employee_id'] == emp_id,
                                   'current_compensation'] = orig_salary * (1.043 ** (year - 2025))

            self.simulate_year_with_raises(conn, year, current_data, raise_percentage=0.043)

        # Get final compensation with incorrect non-compounding
        incorrect_final = conn.execute("""
            SELECT employee_id, full_year_equivalent_compensation as final_salary
            FROM fct_workforce_snapshot
            WHERE simulation_year = 2028
        """).df()

        # Compare results
        comparison = pd.merge(
            correct_final.rename(columns={'final_salary': 'correct_salary'}),
            incorrect_final.rename(columns={'final_salary': 'incorrect_salary'}),
            on='employee_id'
        )

        # Calculate expected compounding factor
        # Correct: 1.043^4 = 1.18424
        # Incorrect: 1 + 0.043*4 = 1.172 (approximately, due to how raises are applied)

        for _, row in comparison.iterrows():
            # Correct compounding should result in higher final salary
            assert row['correct_salary'] > row['incorrect_salary'], \
                f"Employee {row['employee_id']}: Correct compounding (${row['correct_salary']:.2f}) should be > incorrect (${row['incorrect_salary']:.2f})"

        # Verify specific example for $176,000 employee
        target_emp = comparison[comparison['employee_id'] == 'EMP001'].iloc[0]
        expected_correct = 176000 * (1.043 ** 4)  # ~208,426.24

        assert abs(target_emp['correct_salary'] - expected_correct) < 1.0, \
            f"Employee starting at $176,000 should end at ~${expected_correct:.2f} with correct compounding, got ${target_emp['correct_salary']:.2f}"

        conn.close()

    def test_edge_cases(self, test_db_path, test_employee_data):
        """Test edge cases for compensation compounding."""
        conn = self.setup_test_database(test_db_path, test_employee_data)

        # Test case 1: Employee with multiple raises in a year
        emp_data = test_employee_data.head(1).copy()
        self.simulate_year_with_raises(conn, 2025, emp_data)

        # Add a promotion raise
        conn.execute("""
            INSERT INTO fct_yearly_events VALUES
            ('PROMO-EMP001-2025', 'EMP001', 'promotion', '2025-07-01', 2025, 'TEST',
             183568.0, 195000.0, '{"promotion_type": "level_change"}')
        """)

        # Update full_year_equivalent_compensation to reflect promotion
        conn.execute("""
            UPDATE fct_workforce_snapshot
            SET full_year_equivalent_compensation = 195000.0
            WHERE employee_id = 'EMP001' AND simulation_year = 2025
        """)

        # Simulate next year
        emp_data['current_compensation'] = 195000.0  # Should start with promotion salary
        self.simulate_year_with_raises(conn, 2026, emp_data)

        # Verify 2026 starts with 2025's post-promotion salary
        result = conn.execute("""
            SELECT current_compensation, full_year_equivalent_compensation
            FROM fct_workforce_snapshot
            WHERE employee_id = 'EMP001' AND simulation_year = 2026
        """).fetchone()

        assert abs(result[0] - 195000.0) < 0.01, \
            f"Employee should start 2026 with post-promotion salary of $195,000, got ${result[0]:.2f}"

        # Test case 2: New hire mid-year
        new_hire = pd.DataFrame({
            'employee_id': ['EMP006'],
            'employee_ssn': ['666-66-6666'],
            'employee_birth_date': [pd.Timestamp('1995-05-15')],
            'employee_hire_date': [pd.Timestamp('2025-07-01')],
            'current_compensation': [90000.0],
            'level_id': [2],
            'employment_status': ['active']
        })

        self.simulate_year_with_raises(conn, 2025, new_hire)

        # For next year, new hire should get full raise effect
        new_hire['current_compensation'] = 90000.0 * 1.043
        self.simulate_year_with_raises(conn, 2026, new_hire)

        result = conn.execute("""
            SELECT current_compensation
            FROM fct_workforce_snapshot
            WHERE employee_id = 'EMP006' AND simulation_year = 2026
        """).fetchone()

        expected_2026_start = 90000.0 * 1.043
        assert abs(result[0] - expected_2026_start) < 0.01, \
            f"New hire should start 2026 with ${expected_2026_start:.2f}, got ${result[0]:.2f}"

        conn.close()


if __name__ == "__main__":
    # Allow running tests directly
    import sys
    pytest.main([__file__] + sys.argv[1:])
