#!/usr/bin/env python3
"""
Integration tests for the Eligibility Engine (Epic E022: Story S022-01).

Tests the complete eligibility determination system including:
- Integration with MVP orchestrator multi-year framework
- dbt model execution and materialization
- Event generation and storage in fct_yearly_events
- Performance with realistic dataset sizes
"""

import os
import tempfile
import time
from datetime import date, datetime
from unittest.mock import Mock, patch

import pandas as pd
import pytest
from orchestrator_mvp.core.database_manager import (clear_database,
                                                    get_connection)
# Import orchestrator components
from orchestrator_mvp.core.eligibility_engine import (
    EligibilityEngine, process_eligibility_for_year)
from orchestrator_mvp.core.event_emitter import store_events_in_database


class TestEligibilityEngineIntegration:
    """Integration test suite for eligibility engine with database operations."""

    def setup_method(self):
        """Set up test database and sample data."""
        clear_database()

        # Create test workforce data
        conn = get_connection()
        try:
            # Create baseline workforce table with test data
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS int_baseline_workforce (
                    employee_id VARCHAR,
                    employee_ssn VARCHAR,
                    employee_hire_date DATE,
                    employment_status VARCHAR,
                    current_age INTEGER,
                    current_tenure DOUBLE,
                    level_id INTEGER,
                    current_compensation DOUBLE
                )
            """
            )

            # Insert test employees with various hire dates
            test_employees = [
                (
                    "EMP001",
                    "SSN-001",
                    "2023-01-01",
                    "active",
                    30,
                    2.0,
                    2,
                    75000.0,
                ),  # 2+ years, eligible
                (
                    "EMP002",
                    "SSN-002",
                    "2024-06-01",
                    "active",
                    25,
                    0.5,
                    1,
                    60000.0,
                ),  # 6 months, not eligible
                (
                    "EMP003",
                    "SSN-003",
                    "2024-01-01",
                    "active",
                    35,
                    1.0,
                    3,
                    90000.0,
                ),  # 1 year, eligible
                (
                    "EMP004",
                    "SSN-004",
                    "2024-09-01",
                    "active",
                    28,
                    0.3,
                    2,
                    70000.0,
                ),  # 3 months, not eligible
                (
                    "EMP005",
                    "SSN-005",
                    "2022-01-01",
                    "active",
                    40,
                    3.0,
                    4,
                    120000.0,
                ),  # 3+ years, eligible
            ]

            for emp in test_employees:
                conn.execute(
                    """
                    INSERT INTO int_baseline_workforce VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    emp,
                )

        finally:
            conn.close()

    def teardown_method(self):
        """Clean up test database."""
        clear_database()

    def test_eligibility_determination_with_database(self):
        """Test eligibility determination using real database operations."""
        config = {"eligibility": {"waiting_period_days": 365}}  # 1 year waiting period

        engine = EligibilityEngine(config)

        # Test eligibility determination
        eligibility_df = engine.determine_eligibility(2025)

        # Verify results
        assert len(eligibility_df) == 5  # All active employees

        # Check specific employees
        emp001 = eligibility_df[eligibility_df["employee_id"] == "EMP001"].iloc[0]
        assert emp001["is_eligible"] == True  # Hired 2023-01-01, eligible by 2025
        assert emp001["eligibility_reason"] == "eligible_service_met"

        emp002 = eligibility_df[eligibility_df["employee_id"] == "EMP002"].iloc[0]
        assert emp002["is_eligible"] == False  # Hired 2024-06-01, not eligible by 2025
        assert emp002["eligibility_reason"] == "pending_service_requirement"

        emp003 = eligibility_df[eligibility_df["employee_id"] == "EMP003"].iloc[0]
        assert emp003["is_eligible"] == True  # Hired 2024-01-01, eligible by 2025

    def test_eligibility_event_generation_and_storage(self):
        """Test complete eligibility event generation and storage workflow."""
        config = {"eligibility": {"waiting_period_days": 365}}

        # Generate eligibility events for 2025
        events = process_eligibility_for_year(2025, config)

        # Should have events for employees who became eligible in 2025
        # (not those who were already eligible in 2024)
        assert len(events) >= 1

        # Verify event structure
        event = events[0]
        assert "employee_id" in event
        assert event["event_type"] == "eligibility"
        assert event["simulation_year"] == 2025
        assert event["effective_date"] == date(2025, 1, 1)

        # Store events in database
        store_events_in_database(events, "fct_yearly_events")

        # Verify events were stored
        conn = get_connection()
        try:
            stored_events = conn.execute(
                """
                SELECT * FROM fct_yearly_events
                WHERE event_type = 'eligibility' AND simulation_year = 2025
            """
            ).df()

            assert len(stored_events) == len(events)
            assert stored_events.iloc[0]["event_type"] == "eligibility"

        finally:
            conn.close()

    def test_multi_year_eligibility_progression(self):
        """Test eligibility progression across multiple simulation years."""
        config = {"eligibility": {"waiting_period_days": 365}}

        # Test eligibility for multiple years
        years_to_test = [2025, 2026, 2027]
        events_by_year = {}

        for year in years_to_test:
            events = process_eligibility_for_year(year, config)
            events_by_year[year] = events

        # Verify that employees become eligible in different years
        # based on their hire dates

        # 2025: Should have some newly eligible employees
        assert len(events_by_year[2025]) >= 1

        # 2026: Should have fewer newly eligible (most already eligible)
        # 2027: Should have even fewer newly eligible

        # Verify no duplicate eligibility events for same employee
        all_eligible_employees = set()
        for year, events in events_by_year.items():
            year_employees = {event["employee_id"] for event in events}

            # No employee should become eligible twice
            overlap = all_eligible_employees.intersection(year_employees)
            assert (
                len(overlap) == 0
            ), f"Employee(s) {overlap} became eligible multiple times"

            all_eligible_employees.update(year_employees)

    def test_immediate_eligibility_configuration(self):
        """Test eligibility engine with immediate eligibility (0 days)."""
        config = {"eligibility": {"waiting_period_days": 0}}  # Immediate eligibility

        engine = EligibilityEngine(config)

        # All active employees should be eligible immediately
        eligibility_df = engine.determine_eligibility(2025)

        # Verify all employees are eligible
        eligible_count = eligibility_df["is_eligible"].sum()
        total_count = len(eligibility_df)
        assert (
            eligible_count == total_count
        ), f"Only {eligible_count}/{total_count} eligible with immediate eligibility"

        # Verify all have correct reason
        for _, row in eligibility_df.iterrows():
            assert row["eligibility_reason"] == "eligible_service_met"

    def test_custom_waiting_period(self):
        """Test eligibility engine with custom waiting period."""
        config = {"eligibility": {"waiting_period_days": 180}}  # 6 months

        engine = EligibilityEngine(config)
        eligibility_df = engine.determine_eligibility(2025)

        # With 6-month waiting period, more employees should be eligible
        eligible_count = eligibility_df["is_eligible"].sum()

        # Should be more than with 1-year waiting period
        assert (
            eligible_count >= 3
        ), f"Expected at least 3 eligible with 6-month waiting period, got {eligible_count}"

    def test_eligibility_engine_performance_integration(self):
        """Test eligibility engine performance with larger dataset."""
        # Create larger test dataset
        conn = get_connection()
        try:
            # Clear existing data
            conn.execute("DELETE FROM int_baseline_workforce")

            # Insert 1000 test employees
            import random

            random.seed(42)  # Deterministic test data

            for i in range(1000):
                # Random hire dates over past 3 years
                hire_year = random.choice([2022, 2023, 2024])
                hire_month = random.randint(1, 12)
                hire_day = random.randint(1, 28)

                conn.execute(
                    """
                    INSERT INTO int_baseline_workforce VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        f"EMP{i:04d}",
                        f"SSN-{i:04d}",
                        f"{hire_year}-{hire_month:02d}-{hire_day:02d}",
                        "active",
                        random.randint(22, 65),  # age
                        random.uniform(0.1, 5.0),  # tenure
                        random.randint(1, 5),  # level
                        random.uniform(50000, 150000),  # compensation
                    ),
                )

        finally:
            conn.close()

        config = {"eligibility": {"waiting_period_days": 365}}

        # Time the eligibility determination
        start_time = time.time()
        events = process_eligibility_for_year(2025, config)
        end_time = time.time()

        processing_time = end_time - start_time

        # Performance target: <5 seconds for 1K employees
        assert (
            processing_time < 5.0
        ), f"Processing 1000 employees took {processing_time:.2f} seconds, expected <5 seconds"

        # Verify reasonable number of events generated
        assert len(events) > 0, "No eligibility events generated"
        assert len(events) <= 1000, f"Too many events generated: {len(events)}"

        print(
            f"✅ Performance test: Processed 1000 employees in {processing_time:.3f} seconds"
        )
        print(f"   Generated {len(events)} eligibility events")

    def test_eligibility_validation_and_error_handling(self):
        """Test eligibility engine validation and error handling."""
        # Test with invalid configuration
        invalid_config = {"eligibility": {"waiting_period_days": -1}}

        with pytest.raises(ValueError):
            EligibilityEngine(invalid_config)

        # Test with missing database table
        clear_database()  # Remove all tables

        config = {"eligibility": {"waiting_period_days": 365}}

        engine = EligibilityEngine(config)

        # Should handle missing table gracefully
        with pytest.raises(Exception):  # Database error expected
            engine.determine_eligibility(2025)

    def test_eligibility_edge_cases(self):
        """Test eligibility engine with edge cases."""
        # Create edge case data
        conn = get_connection()
        try:
            conn.execute("DELETE FROM int_baseline_workforce")

            # Edge cases:
            edge_cases = [
                (
                    "EDGE001",
                    "SSN-E01",
                    "2024-12-31",
                    "active",
                    25,
                    0.0,
                    1,
                    60000.0,
                ),  # Hired on Dec 31
                (
                    "EDGE002",
                    "SSN-E02",
                    "2024-01-01",
                    "active",
                    65,
                    1.0,
                    5,
                    200000.0,
                ),  # Exactly 1 year
                (
                    "EDGE003",
                    "SSN-E03",
                    "2024-01-02",
                    "active",
                    21,
                    1.0,
                    1,
                    50000.0,
                ),  # 1 day short of 1 year
            ]

            for emp in edge_cases:
                conn.execute(
                    """
                    INSERT INTO int_baseline_workforce VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    emp,
                )

        finally:
            conn.close()

        config = {"eligibility": {"waiting_period_days": 365}}

        engine = EligibilityEngine(config)
        eligibility_df = engine.determine_eligibility(2025)

        # Verify edge cases
        edge001 = eligibility_df[eligibility_df["employee_id"] == "EDGE001"].iloc[0]
        assert (
            edge001["is_eligible"] == False
        )  # Hired Dec 31, 2024 - not eligible until 2026

        edge002 = eligibility_df[eligibility_df["employee_id"] == "EDGE002"].iloc[0]
        assert edge002["is_eligible"] == True  # Hired Jan 1, 2024 - exactly 1 year

        edge003 = eligibility_df[eligibility_df["employee_id"] == "EDGE003"].iloc[0]
        assert edge003["is_eligible"] == False  # Hired Jan 2, 2024 - 1 day short


class TestEligibilityEngineDataQuality:
    """Test suite for eligibility engine data quality and validation."""

    def test_event_data_quality_flags(self):
        """Test that eligibility events have proper data quality flags."""
        # Set up test data
        clear_database()
        conn = get_connection()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS int_baseline_workforce (
                    employee_id VARCHAR,
                    employee_ssn VARCHAR,
                    employee_hire_date DATE,
                    employment_status VARCHAR,
                    current_age INTEGER,
                    current_tenure DOUBLE,
                    level_id INTEGER,
                    current_compensation DOUBLE
                )
            """
            )

            conn.execute(
                """
                INSERT INTO int_baseline_workforce VALUES
                ('TEST001', 'SSN-T01', '2024-01-01', 'active', 30, 1.0, 2, 75000.0)
            """
            )
        finally:
            conn.close()

        config = {"eligibility": {"waiting_period_days": 365}}

        events = process_eligibility_for_year(2025, config)

        # Verify data quality fields
        for event in events:
            assert event["data_quality_flag"] == "VALID"
            assert event["parameter_source"] == "eligibility_engine"
            assert event["parameter_scenario_id"] == "eligibility_mvp"
            assert isinstance(event["created_at"], datetime)
            assert event["event_sequence"] == 6  # After promotions, before enrollments

    def test_eligibility_audit_trail(self):
        """Test that eligibility events create proper audit trail."""
        clear_database()
        conn = get_connection()
        try:
            # Set up test data
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS int_baseline_workforce (
                    employee_id VARCHAR,
                    employee_ssn VARCHAR,
                    employee_hire_date DATE,
                    employment_status VARCHAR,
                    current_age INTEGER,
                    current_tenure DOUBLE,
                    level_id INTEGER,
                    current_compensation DOUBLE
                )
            """
            )

            conn.execute(
                """
                INSERT INTO int_baseline_workforce VALUES
                ('AUDIT001', 'SSN-A01', '2024-01-01', 'active', 30, 1.0, 2, 75000.0)
            """
            )

            # Generate and store events
            config = {"eligibility": {"waiting_period_days": 365}}
            events = process_eligibility_for_year(2025, config)
            store_events_in_database(events, "fct_yearly_events")

            # Verify audit trail in database
            audit_data = conn.execute(
                """
                SELECT
                    employee_id,
                    event_type,
                    simulation_year,
                    effective_date,
                    event_details,
                    created_at,
                    parameter_source,
                    data_quality_flag
                FROM fct_yearly_events
                WHERE event_type = 'eligibility'
                ORDER BY created_at
            """
            ).df()

            assert len(audit_data) > 0

            # Verify audit fields
            audit_event = audit_data.iloc[0]
            assert audit_event["employee_id"] == "AUDIT001"
            assert audit_event["event_type"] == "eligibility"
            assert audit_event["simulation_year"] == 2025
            assert audit_event["parameter_source"] == "eligibility_engine"
            assert audit_event["data_quality_flag"] == "VALID"

        finally:
            conn.close()


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v"])
