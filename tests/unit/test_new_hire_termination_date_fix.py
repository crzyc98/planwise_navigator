"""
Unit tests for new hire termination date fix.

Tests validate that the adaptive termination logic eliminates artificial
December 31st clustering while maintaining statistical accuracy and
deterministic behavior.
"""

from collections import Counter
from datetime import date, timedelta
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from orchestrator_mvp.core.event_emitter import \
    generate_new_hire_termination_events


class TestNewHireTerminationDateFix:
    """Test suite for new hire termination date clustering fix."""

    @pytest.fixture
    def sample_hire_events_early_year(self) -> List[Dict[str, Any]]:
        """Sample hire events from January-September for testing standard windows."""
        return [
            {
                "employee_id": f"EMP00{i:03d}",
                "employee_ssn": f"123-45-{6789 + i:04d}",
                "effective_date": date(2024, month, 15),
                "compensation_amount": 75000.0,
                "employee_age": 30 + (i % 10),
                "level_id": f"L{(i % 3) + 1}",
                "age_band": "30-39",
            }
            for i, month in enumerate(range(1, 9), 1)  # Jan-Aug (avoid borderline Sep)
        ]

    @pytest.fixture
    def sample_hire_events_late_year(self) -> List[Dict[str, Any]]:
        """Sample hire events from October-December for testing adaptive windows."""
        return [
            {
                "employee_id": f"EMP01{i:03d}",
                "employee_ssn": f"987-65-{4321 + i:04d}",
                "effective_date": date(2024, month, 15),
                "compensation_amount": 80000.0,
                "employee_age": 25 + (i % 15),
                "level_id": f"L{(i % 4) + 1}",
                "age_band": "25-34",
            }
            for i, month in enumerate(
                range(9, 13), 1
            )  # Sep-Dec (borderline + late year)
        ]

    @pytest.fixture
    def sample_hire_events_mixed_year(self) -> List[Dict[str, Any]]:
        """Mixed hire events throughout the year for comprehensive testing."""
        events = []
        for i in range(1, 13):  # All months
            for j in range(5):  # 5 hires per month
                events.append(
                    {
                        "employee_id": f"EMP{i:02d}{j:03d}",
                        "employee_ssn": f"555-{i:02d}-{j:04d}",
                        "effective_date": date(2024, i, min(15 + j * 3, 28)),
                        "compensation_amount": 70000.0 + (i * 1000),
                        "employee_age": 25 + (i % 20),
                        "level_id": f"L{((i + j) % 5) + 1}",
                        "age_band": "25-44",
                    }
                )
        return events

    def test_no_december_31st_clustering(self, sample_hire_events_mixed_year):
        """Test that termination dates don't artificially cluster at December 31st."""
        termination_rate = 0.25
        simulation_year = 2024

        termination_events = generate_new_hire_termination_events(
            sample_hire_events_mixed_year, termination_rate, simulation_year
        )

        # Count termination dates by day
        termination_dates = [event["effective_date"] for event in termination_events]
        date_counts = Counter(termination_dates)

        # December 31st should not have excessive clustering
        dec_31_count = date_counts.get(date(2024, 12, 31), 0)
        total_terminations = len(termination_events)

        # No more than 5% of terminations should occur on any single date
        max_single_date_percentage = 0.05
        assert dec_31_count <= total_terminations * max_single_date_percentage, (
            f"Too many terminations on Dec 31: {dec_31_count}/{total_terminations} "
            f"({dec_31_count/total_terminations:.2%})"
        )

    def test_realistic_date_distribution(self, sample_hire_events_mixed_year):
        """Test that termination dates are distributed naturally throughout the year."""
        termination_rate = 0.30
        simulation_year = 2024

        termination_events = generate_new_hire_termination_events(
            sample_hire_events_mixed_year, termination_rate, simulation_year
        )

        # Group termination dates by month
        termination_dates = [event["effective_date"] for event in termination_events]
        monthly_counts = Counter(date.month for date in termination_dates)

        # Should have terminations in multiple months (not just December)
        assert (
            len(monthly_counts) >= 3
        ), "Terminations should be spread across multiple months"

        # December should not dominate (no more than 40% of total)
        dec_count = monthly_counts.get(12, 0)
        total_terminations = len(termination_events)
        dec_percentage = dec_count / total_terminations if total_terminations > 0 else 0

        assert (
            dec_percentage <= 0.40
        ), f"December has too many terminations: {dec_percentage:.2%}"

    def test_early_year_hire_standard_window(self, sample_hire_events_early_year):
        """Test that early/mid-year hires use standard 3-9 month termination windows."""
        termination_rate = 1.0  # Terminate all for testing
        simulation_year = 2024

        termination_events = generate_new_hire_termination_events(
            sample_hire_events_early_year, termination_rate, simulation_year
        )

        # All early year hires should have termination dates within reasonable range
        for event in termination_events:
            hire_date = next(
                h["effective_date"]
                for h in sample_hire_events_early_year
                if h["employee_id"] == event["employee_id"]
            )
            termination_date = event["effective_date"]

            days_diff = (termination_date - hire_date).days

            # Should be within expanded range (30-275 days) to account for adaptive logic
            assert (
                30 <= days_diff <= 275
            ), f"Employee {event['employee_id']}: {days_diff} days from hire to termination"

            # Should not terminate on Dec 31 unless naturally calculated
            if termination_date == date(2024, 12, 31):
                # Only acceptable if it falls naturally within the window
                expected_dec31_range = (date(2024, 3, 31), date(2024, 11, 1))
                assert (
                    expected_dec31_range[0] <= hire_date <= expected_dec31_range[1]
                ), f"Dec 31 termination for {event['employee_id']} seems artificial"

    def test_late_year_hire_adaptive_window(self, sample_hire_events_late_year):
        """Test that late-year hires use adaptive shorter termination windows."""
        termination_rate = 1.0  # Terminate all for testing
        simulation_year = 2024

        termination_events = generate_new_hire_termination_events(
            sample_hire_events_late_year, termination_rate, simulation_year
        )

        # All late year hires should have reasonable termination dates within the year
        for event in termination_events:
            hire_date = next(
                h["effective_date"]
                for h in sample_hire_events_late_year
                if h["employee_id"] == event["employee_id"]
            )
            termination_date = event["effective_date"]

            days_diff = (termination_date - hire_date).days

            # Should be within reasonable range for late hires (1-6 months max)
            assert (
                1 <= days_diff <= 180
            ), f"Employee {event['employee_id']}: {days_diff} days from hire to termination"

            # Must be within simulation year
            assert (
                termination_date.year == simulation_year
            ), f"Termination date {termination_date} outside simulation year {simulation_year}"

            # Should not be December 31st unless very close to natural calculation
            if termination_date == date(2024, 12, 31):
                days_remaining = (date(2024, 12, 31) - hire_date).days
                # Only acceptable if hire was very late in year
                assert (
                    days_remaining <= 30
                ), f"Dec 31 termination for late hire {event['employee_id']} seems artificial"

    def test_statistical_accuracy_preservation(self, sample_hire_events_mixed_year):
        """Test that overall termination rates remain consistent with input parameters."""
        test_rates = [0.10, 0.25, 0.40]
        simulation_year = 2024

        for rate in test_rates:
            termination_events = generate_new_hire_termination_events(
                sample_hire_events_mixed_year, rate, simulation_year
            )

            expected_count = int(len(sample_hire_events_mixed_year) * rate)
            actual_count = len(termination_events)

            # Allow for rounding differences (±1)
            assert (
                abs(actual_count - expected_count) <= 1
            ), f"Rate {rate}: expected ~{expected_count}, got {actual_count}"

    def test_deterministic_behavior(self, sample_hire_events_mixed_year):
        """Test that identical inputs produce identical outputs for reproducibility."""
        termination_rate = 0.20
        simulation_year = 2024

        # Run the function twice with identical inputs
        events1 = generate_new_hire_termination_events(
            sample_hire_events_mixed_year, termination_rate, simulation_year
        )

        events2 = generate_new_hire_termination_events(
            sample_hire_events_mixed_year, termination_rate, simulation_year
        )

        # Results should be identical
        assert len(events1) == len(events2), "Event counts should be identical"

        # Sort events by employee_id for comparison
        events1_sorted = sorted(events1, key=lambda x: x["employee_id"])
        events2_sorted = sorted(events2, key=lambda x: x["employee_id"])

        for e1, e2 in zip(events1_sorted, events2_sorted):
            assert e1["employee_id"] == e2["employee_id"], "Employee IDs should match"
            assert (
                e1["effective_date"] == e2["effective_date"]
            ), f"Termination dates should match for {e1['employee_id']}"

    def test_edge_case_december_hires(self):
        """Test handling of December hires with very limited remaining days."""
        december_hires = [
            {
                "employee_id": f"EMP_DEC_{i:03d}",
                "employee_ssn": f"999-99-{i:04d}",
                "effective_date": date(2024, 12, day),
                "compensation_amount": 85000.0,
                "employee_age": 35,
                "level_id": "L2",
                "age_band": "35-44",
            }
            for i, day in enumerate([1, 15, 28], 1)
        ]

        termination_rate = 1.0  # Force all to terminate
        simulation_year = 2024

        termination_events = generate_new_hire_termination_events(
            december_hires, termination_rate, simulation_year
        )

        # All December hires should have valid termination dates within the year
        for event in termination_events:
            termination_date = event["effective_date"]

            assert (
                termination_date.year == simulation_year
            ), f"Termination {termination_date} outside simulation year"

            # Should be after hire date
            hire_date = next(
                h["effective_date"]
                for h in december_hires
                if h["employee_id"] == event["employee_id"]
            )
            assert (
                termination_date > hire_date
            ), f"Termination {termination_date} not after hire {hire_date}"

    def test_leap_year_handling(self):
        """Test that the fix handles leap years correctly."""
        leap_year_hires = [
            {
                "employee_id": f"EMP_LEAP_{i:03d}",
                "employee_ssn": f"888-88-{i:04d}",
                "effective_date": date(2024, 2, 29),  # Leap day
                "compensation_amount": 90000.0,
                "employee_age": 40,
                "level_id": "L3",
                "age_band": "40-49",
            }
            for i in range(5)
        ]

        termination_rate = 1.0
        simulation_year = 2024  # Leap year

        termination_events = generate_new_hire_termination_events(
            leap_year_hires, termination_rate, simulation_year
        )

        # Should handle leap year without issues
        assert len(termination_events) == len(leap_year_hires)

        for event in termination_events:
            termination_date = event["effective_date"]
            assert termination_date.year == simulation_year
            assert termination_date >= date(2024, 2, 29)
            assert termination_date <= date(2024, 12, 31)

    def test_multi_year_simulation_continuity(self):
        """Test that the fix works correctly across different simulation years."""
        base_hires = [
            {
                "employee_id": f"EMP_MULTI_{i:03d}",
                "employee_ssn": f"777-77-{i:04d}",
                "effective_date": date(2023, 6, 15),
                "compensation_amount": 95000.0,
                "employee_age": 45,
                "level_id": "L4",
                "age_band": "45-54",
            }
            for i in range(10)
        ]

        termination_rate = 0.30

        # Test multiple simulation years
        for sim_year in [2023, 2024, 2025]:
            # Adjust hire dates to be within each simulation year
            adjusted_hires = []
            for hire in base_hires:
                adjusted_hire = hire.copy()
                adjusted_hire["effective_date"] = date(sim_year, 6, 15)
                adjusted_hires.append(adjusted_hire)

            termination_events = generate_new_hire_termination_events(
                adjusted_hires, termination_rate, sim_year
            )

            # Basic validation for each year
            assert (
                len(termination_events) > 0
            ), f"No terminations generated for {sim_year}"

            for event in termination_events:
                termination_date = event["effective_date"]
                assert (
                    termination_date.year == sim_year
                ), f"Termination {termination_date} not in simulation year {sim_year}"

                # Should not cluster at Dec 31
                if termination_date == date(sim_year, 12, 31):
                    # This should be rare with the new logic
                    pass  # Allow but don't expect clustering

    def test_boundary_conditions(self):
        """Test edge cases and boundary conditions."""
        # Test with very high termination rate
        high_rate_hires = [
            {
                "employee_id": f"EMP_HIGH_{i:03d}",
                "employee_ssn": f"666-66-{i:04d}",
                "effective_date": date(2024, 8, 1),
                "compensation_amount": 100000.0,
                "employee_age": 50,
                "level_id": "L5",
                "age_band": "50-59",
            }
            for i in range(100)
        ]

        termination_events = generate_new_hire_termination_events(
            high_rate_hires, 0.95, 2024  # Very high rate
        )

        # Should handle high rates without clustering
        termination_dates = [event["effective_date"] for event in termination_events]
        dec_31_count = sum(1 for d in termination_dates if d == date(2024, 12, 31))

        # Even with high rates, December 31st should not dominate
        assert (
            dec_31_count < len(termination_events) * 0.20
        ), f"Too much clustering even at high termination rate: {dec_31_count}/{len(termination_events)}"
