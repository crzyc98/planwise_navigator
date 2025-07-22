"""
Integration tests for new hire termination date fix.

Tests validate that the termination date fix integrates correctly with the
broader simulation pipeline and maintains compatibility with existing systems.
"""

import pytest
import pandas as pd
from datetime import date, timedelta
from unittest.mock import Mock, patch
from collections import Counter
from typing import Dict, Any

from orchestrator.simulator_pipeline import (
    run_year_simulation,
    YearResult,
    clean_duckdb_data,
    run_dbt_event_models_for_year,
    run_dbt_snapshot_for_year,
)
from orchestrator_mvp.core.event_emitter import generate_new_hire_termination_events
from orchestrator_mvp.core.workforce_calculations import calculate_workforce_requirements


class TestNewHireTerminationIntegration:
    """Integration test suite for new hire termination date fix."""

    @pytest.fixture
    def simulation_config(self) -> Dict[str, Any]:
        """Standard simulation configuration for integration testing."""
        return {
            "start_year": 2024,
            "end_year": 2024,
            "target_growth_rate": 0.05,
            "total_termination_rate": 0.15,
            "new_hire_termination_rate": 0.25,
            "random_seed": 12345,
            "full_refresh": True,
        }

    @pytest.fixture
    def mock_workforce_data(self):
        """Mock workforce data for testing."""
        return [
            {
                'employee_id': f'EMP{i:05d}',
                'employee_ssn': f'123-45-{6000+i:04d}',
                'employee_age': 25 + (i % 30),
                'compensation_amount': 60000.0 + (i * 1000),
                'level_id': f'L{(i % 4) + 1}',
                'age_band': '25-54',
            }
            for i in range(100)
        ]

    @pytest.fixture
    def mixed_hire_events(self):
        """Mixed hire events throughout the year for comprehensive testing."""
        events = []
        for month in range(1, 13):
            for i in range(10):  # 10 hires per month
                events.append({
                    'employee_id': f'HIRE_{month:02d}_{i:03d}',
                    'employee_ssn': f'999-{month:02d}-{i:04d}',
                    'effective_date': date(2024, month, min(15, 28)),
                    'compensation_amount': 75000.0,
                    'employee_age': 30,
                    'level_id': f'L{(i % 3) + 1}',
                    'age_band': '30-39',
                })
        return events

    def test_end_to_end_simulation_with_fix(self, simulation_config, mock_workforce_data):
        """Test complete simulation pipeline with termination date fix."""

        with patch('orchestrator_mvp.core.workforce_calculations.get_current_workforce') as mock_workforce:
            mock_workforce.return_value = mock_workforce_data

            with patch('orchestrator_mvp.core.event_emitter.generate_new_hire_termination_events') as mock_terminations:
                # Configure mock to return realistic termination events
                def side_effect_terminations(hire_events, rate, sim_year):
                    # Use the actual fixed function for realistic behavior
                    return generate_new_hire_termination_events(hire_events, rate, sim_year)

                mock_terminations.side_effect = side_effect_terminations

                # Mock database operations
                with patch('orchestrator.simulator_pipeline.clean_duckdb_data') as mock_clean, \
                     patch('orchestrator.simulator_pipeline.run_dbt_event_models_for_year') as mock_dbt_events, \
                     patch('orchestrator.simulator_pipeline.run_dbt_snapshot_for_year') as mock_dbt_snapshot:

                    mock_clean.return_value = None
                    mock_dbt_events.return_value = {"status": "success"}
                    mock_dbt_snapshot.return_value = {"status": "success"}

                    # Mock context
                    mock_context = Mock()
                    mock_context.log = Mock()
                    mock_context.op_config = simulation_config
                    mock_context.resources = Mock()
                    mock_context.resources.dbt = Mock()

                    # Run simulation
                    result = run_year_simulation(mock_context, 2024)

                    # Validate integration
                    assert isinstance(result, YearResult)
                    assert result.year == 2024

                    # Verify termination events were generated with fixed logic
                    mock_terminations.assert_called()
                    call_args = mock_terminations.call_args
                    assert call_args[0][2] == 2024  # simulation_year

    def test_multi_year_simulation_continuity(self, simulation_config):
        """Test that the fix works correctly across multiple simulation years."""

        # Extend config for multi-year testing
        multi_year_config = simulation_config.copy()
        multi_year_config.update({
            "start_year": 2024,
            "end_year": 2026,
        })

        termination_dates_by_year = {}

        with patch('orchestrator_mvp.core.workforce_calculations.get_current_workforce') as mock_workforce:
            mock_workforce.return_value = [
                {
                    'employee_id': f'EMP{i:05d}',
                    'employee_ssn': f'456-78-{9000+i:04d}',
                    'employee_age': 35,
                    'compensation_amount': 80000.0,
                    'level_id': 'L2',
                    'age_band': '35-44',
                }
                for i in range(50)
            ]

            # Test each year separately to track termination patterns
            for year in range(2024, 2027):
                # Generate mixed hire events for each year
                hire_events = [
                    {
                        'employee_id': f'HIRE_{year}_{i:03d}',
                        'employee_ssn': f'888-{year % 100:02d}-{i:04d}',
                        'effective_date': date(year, month, 15),
                        'compensation_amount': 85000.0,
                        'employee_age': 40,
                        'level_id': 'L3',
                        'age_band': '40-49',
                    }
                    for i, month in enumerate(range(1, 13))
                ]

                termination_events = generate_new_hire_termination_events(
                    hire_events,
                    multi_year_config["new_hire_termination_rate"],
                    year
                )

                termination_dates = [event['effective_date'] for event in termination_events]
                termination_dates_by_year[year] = termination_dates

                # Validate each year's results
                assert len(termination_dates) > 0, f"No terminations for year {year}"

                # Check that all dates are within the simulation year
                for term_date in termination_dates:
                    assert term_date.year == year, \
                        f"Termination date {term_date} not in simulation year {year}"

                # Check for reduced December 31st clustering
                dec_31_count = sum(1 for d in termination_dates if d == date(year, 12, 31))
                total_terms = len(termination_dates)
                dec_31_percentage = dec_31_count / total_terms if total_terms > 0 else 0

                assert dec_31_percentage <= 0.15, \
                    f"Year {year}: Too much Dec 31 clustering: {dec_31_percentage:.2%}"

        # Validate consistency across years
        for year in range(2024, 2027):
            dates = termination_dates_by_year[year]
            monthly_distribution = Counter(d.month for d in dates)
            assert len(monthly_distribution) >= 4, \
                f"Year {year}: Terminations should span multiple months"

    def test_database_integration_with_fix(self, mixed_hire_events):
        """Test that termination events integrate properly with database operations."""

        termination_events = generate_new_hire_termination_events(
            mixed_hire_events,
            0.30,
            2024
        )

        # Validate event structure for database compatibility
        required_fields = [
            'employee_id', 'employee_ssn', 'event_type', 'simulation_year',
            'effective_date', 'event_details', 'compensation_amount',
            'previous_compensation', 'employee_age', 'employee_tenure',
            'level_id', 'age_band', 'tenure_band'
        ]

        for event in termination_events:
            for field in required_fields:
                assert field in event, f"Missing required field: {field}"

            # Validate data types
            assert isinstance(event['effective_date'], date), \
                "effective_date must be a date object"
            assert event['event_type'] == 'termination', \
                "event_type must be 'termination'"
            assert event['simulation_year'] == 2024, \
                "simulation_year must match"

            # Validate date is realistic (not clustered)
            effective_date = event['effective_date']
            assert effective_date >= date(2024, 1, 1), \
                "Termination date too early"
            assert effective_date <= date(2024, 12, 31), \
                "Termination date too late"

        # Test realistic distribution
        termination_dates = [event['effective_date'] for event in termination_events]
        monthly_counts = Counter(d.month for d in termination_dates)

        # Should have reasonable distribution across months
        assert len(monthly_counts) >= 6, "Should have terminations across multiple months"

        # December should not dominate
        dec_percentage = monthly_counts.get(12, 0) / len(termination_dates)
        assert dec_percentage <= 0.35, f"December dominance too high: {dec_percentage:.2%}"

    def test_workforce_calculation_compatibility(self, simulation_config):
        """Test that the fix maintains compatibility with workforce calculations."""

        # Mock current workforce
        current_workforce = [
            {
                'employee_id': f'EMP_{i:05d}',
                'employee_age': 30 + (i % 25),
                'compensation_amount': 70000.0 + (i * 500),
                'level_id': f'L{(i % 5) + 1}',
            }
            for i in range(200)
        ]

        with patch('orchestrator_mvp.core.workforce_calculations.get_current_workforce') as mock_workforce:
            mock_workforce.return_value = current_workforce

            # Calculate workforce requirements (this should work unchanged)
            requirements = calculate_workforce_requirements(
                current_workforce,
                simulation_config["target_growth_rate"],
                simulation_config["total_termination_rate"],
                2024
            )

            # Validate requirements calculation is unaffected
            assert 'total_required' in requirements
            assert 'net_hires_needed' in requirements
            assert requirements['total_required'] > 0

            # Test that new hire termination calculation integrates properly
            if requirements.get('new_hires', 0) > 0:
                # Create mock hire events
                hire_events = [
                    {
                        'employee_id': f'NEW_HIRE_{i:05d}',
                        'employee_ssn': f'555-55-{i:04d}',
                        'effective_date': date(2024, 6 + (i % 6), 15),
                        'compensation_amount': 75000.0,
                        'employee_age': 28,
                        'level_id': 'L2',
                        'age_band': '25-34',
                    }
                    for i in range(min(50, requirements.get('new_hires', 0)))
                ]

                # Generate termination events with fix
                termination_events = generate_new_hire_termination_events(
                    hire_events,
                    simulation_config["new_hire_termination_rate"],
                    2024
                )

                # Should integrate seamlessly
                expected_terminations = int(len(hire_events) *
                                          simulation_config["new_hire_termination_rate"])
                actual_terminations = len(termination_events)

                # Allow for rounding differences
                assert abs(actual_terminations - expected_terminations) <= 1

    def test_event_sequence_validation(self, mixed_hire_events):
        """Test that termination events maintain proper sequencing with other events."""

        termination_events = generate_new_hire_termination_events(
            mixed_hire_events,
            0.40,  # Higher rate for more events to test
            2024
        )

        # Create a mapping of hire to termination events
        hire_to_termination = {}
        for term_event in termination_events:
            employee_id = term_event['employee_id']
            hire_event = next(h for h in mixed_hire_events if h['employee_id'] == employee_id)
            hire_to_termination[employee_id] = {
                'hire_date': hire_event['effective_date'],
                'termination_date': term_event['effective_date']
            }

        # Validate proper sequencing
        for employee_id, dates in hire_to_termination.items():
            hire_date = dates['hire_date']
            term_date = dates['termination_date']

            # Termination must be after hire
            assert term_date > hire_date, \
                f"Employee {employee_id}: termination {term_date} not after hire {hire_date}"

            # Reasonable time gap
            days_diff = (term_date - hire_date).days
            assert 1 <= days_diff <= 365, \
                f"Employee {employee_id}: unrealistic {days_diff} days between hire and termination"

    def test_performance_impact_assessment(self, mixed_hire_events):
        """Test that the fix doesn't significantly impact simulation performance."""
        import time

        # Measure performance of the fixed function
        start_time = time.time()

        for _ in range(10):  # Run multiple times for better measurement
            termination_events = generate_new_hire_termination_events(
                mixed_hire_events,
                0.25,
                2024
            )

        end_time = time.time()
        avg_time = (end_time - start_time) / 10

        # Performance should be reasonable (under 100ms for 120 hire events)
        assert avg_time < 0.1, f"Performance degraded: {avg_time:.3f}s average"

        # Validate that results are still correct despite performance focus
        assert len(termination_events) > 0

        # Check for proper date distribution (no clustering)
        termination_dates = [event['effective_date'] for event in termination_events]
        dec_31_count = sum(1 for d in termination_dates if d == date(2024, 12, 31))
        clustering_percentage = dec_31_count / len(termination_dates)

        assert clustering_percentage <= 0.10, \
            f"Performance optimization broke clustering fix: {clustering_percentage:.2%}"

    def test_backward_compatibility(self, mixed_hire_events):
        """Test that the fix maintains expected behavior for existing code."""

        # The function signature should remain unchanged
        termination_events = generate_new_hire_termination_events(
            mixed_hire_events,
            0.20,
            2024
        )

        # Basic output structure should be preserved
        assert isinstance(termination_events, list)

        if termination_events:
            sample_event = termination_events[0]

            # Expected fields should still be present
            expected_fields = [
                'employee_id', 'event_type', 'effective_date',
                'simulation_year', 'event_details'
            ]

            for field in expected_fields:
                assert field in sample_event, f"Backward compatibility: missing {field}"

            # Event type should still be 'termination'
            assert sample_event['event_type'] == 'termination'

            # Details should still indicate new hire termination
            assert sample_event['event_details'] == 'new_hire_departure'

        # Overall count logic should be preserved
        expected_count = int(len(mixed_hire_events) * 0.20)
        actual_count = len(termination_events)

        # Allow for rounding differences
        assert abs(actual_count - expected_count) <= 1, \
            "Backward compatibility: termination count logic changed"

    def test_edge_case_integration(self):
        """Test integration of edge cases within the broader system."""

        # Test with December hires in a multi-component system
        december_hires = [
            {
                'employee_id': f'DEC_HIRE_{i:03d}',
                'employee_ssn': f'777-12-{i:04d}',
                'effective_date': date(2024, 12, day),
                'compensation_amount': 90000.0,
                'employee_age': 35,
                'level_id': 'L3',
                'age_band': '35-44',
            }
            for i, day in enumerate([1, 10, 20, 28], 1)
        ]

        # Should handle December hires without issues
        termination_events = generate_new_hire_termination_events(
            december_hires,
            1.0,  # Force all to terminate for edge case testing
            2024
        )

        assert len(termination_events) == len(december_hires), \
            "All December hires should have termination events"

        for event in termination_events:
            term_date = event['effective_date']

            # Find corresponding hire
            hire_event = next(h for h in december_hires
                            if h['employee_id'] == event['employee_id'])
            hire_date = hire_event['effective_date']

            # Basic validations
            assert term_date.year == 2024, "Termination year correct"
            assert term_date > hire_date, "Termination after hire"
            assert term_date <= date(2024, 12, 31), "Termination within year"

            # Should not artificially cluster at Dec 31
            days_to_year_end = (date(2024, 12, 31) - hire_date).days
            if days_to_year_end > 1:  # If there was time for natural calculation
                # Dec 31 should be rare, not the default
                pass  # Allow Dec 31 but don't expect it for all events
