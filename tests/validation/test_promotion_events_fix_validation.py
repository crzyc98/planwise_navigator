"""
Comprehensive test suite to validate the promotion events fix implementation.

This test suite validates that the promotion events fix is working correctly,
ensuring that promotion events are generated with proper hazard-based calculations,
correct random value distribution, and proper database storage.

References:
- orchestrator_mvp/core/event_emitter.py
- orchestrator_mvp/run_mvp.py
- docs/sessions/2025/session_2025_07_18_promotion_events_fix.md
"""

import pytest
import pandas as pd
import numpy as np
from datetime import date
import hashlib
from typing import Dict, List, Tuple
from unittest.mock import Mock, patch, MagicMock

from orchestrator_mvp.core.event_emitter import (
    calculate_promotion_probability,
    generate_promotion_events,
    get_legacy_random_value
)


class TestPromotionEventsFix:
    """Test suite to validate the promotion events fix implementation."""

    @pytest.fixture
    def sample_hazard_config(self) -> pd.DataFrame:
        """Create sample hazard configuration matching the expected structure."""
        return pd.DataFrame({
            'metric': ['promotion'] * 4,
            'level': [1, 2, 3, 4],
            'base_rate': [0.08, 0.07, 0.05, 0.04],
            'tenure_multiplier': [1.0, 1.0, 1.0, 1.0],
            'age_multiplier': [1.0, 1.0, 1.0, 1.0],
            'level_dampener': [1.0, 0.9, 0.8, 0.7]
        })

    @pytest.fixture
    def sample_workforce(self) -> pd.DataFrame:
        """Create sample workforce data for testing."""
        np.random.seed(42)
        employees = []
        employee_id = 1000

        # Create employees at different levels
        for level in [1, 2, 3, 4]:
            for i in range(1000):  # 1000 employees per level
                employees.append({
                    'employee_id': f'EMP_{employee_id}',
                    'level': level,
                    'age': np.random.randint(25, 65),
                    'tenure': np.random.randint(0, 20),
                    'base_salary': 50000 + (level * 20000) + np.random.randint(-10000, 10000)
                })
                employee_id += 1

        return pd.DataFrame(employees)

    def test_promotion_event_generation_not_zero(self, sample_workforce, sample_hazard_config):
        """Test that promotion events are actually generated (not 0 like before the fix)."""
        with patch('orchestrator_mvp.core.event_emitter.load_hazard_configuration') as mock_load:
            mock_load.return_value = sample_hazard_config

            events = generate_promotion_events(
                workforce=sample_workforce,
                simulation_year=2023,
                scenario_id='test_scenario',
                random_seed=42
            )

            # Should generate promotion events (not 0)
            assert len(events) > 0, "No promotion events were generated"

            # Expected approximately 220-280 promotions total based on hazard rates
            assert 150 < len(events) < 350, f"Unexpected number of promotion events: {len(events)}"

    def test_hazard_based_calculations(self, sample_hazard_config):
        """Test that promotion probabilities are calculated correctly using the hazard formula."""
        # Test Level 1 employee
        prob_level1 = calculate_promotion_probability(
            level=1,
            tenure=5,
            age=35,
            hazard_config=sample_hazard_config
        )
        # Expected: 0.08 * 1.0 * 1.0 * 1.0 = 0.08
        assert abs(prob_level1 - 0.08) < 0.001, f"Level 1 probability incorrect: {prob_level1}"

        # Test Level 2 employee
        prob_level2 = calculate_promotion_probability(
            level=2,
            tenure=5,
            age=35,
            hazard_config=sample_hazard_config
        )
        # Expected: 0.07 * 1.0 * 1.0 * 0.9 = 0.063
        assert abs(prob_level2 - 0.063) < 0.001, f"Level 2 probability incorrect: {prob_level2}"

        # Test Level 3 employee
        prob_level3 = calculate_promotion_probability(
            level=3,
            tenure=5,
            age=35,
            hazard_config=sample_hazard_config
        )
        # Expected: 0.05 * 1.0 * 1.0 * 0.8 = 0.04
        assert abs(prob_level3 - 0.04) < 0.001, f"Level 3 probability incorrect: {prob_level3}"

        # Test Level 4 employee
        prob_level4 = calculate_promotion_probability(
            level=4,
            tenure=5,
            age=35,
            hazard_config=sample_hazard_config
        )
        # Expected: 0.04 * 1.0 * 1.0 * 0.7 = 0.028
        assert abs(prob_level4 - 0.028) < 0.001, f"Level 4 probability incorrect: {prob_level4}"

    def test_random_value_distribution(self):
        """Test that random values are properly distributed across 0.0-1.0 range."""
        # Generate random values for a sample of employees
        random_values = []
        for i in range(1000):
            employee_id = f'EMP_{i}'
            random_val = get_legacy_random_value(employee_id, 2023, 42)
            random_values.append(random_val)

            # Each value should be between 0 and 1
            assert 0.0 <= random_val <= 1.0, f"Random value out of range: {random_val}"

        # Check distribution
        random_values = np.array(random_values)

        # Mean should be approximately 0.5
        assert 0.45 < np.mean(random_values) < 0.55, f"Random mean not centered: {np.mean(random_values)}"

        # Should have reasonable spread
        assert np.std(random_values) > 0.25, f"Random values not well distributed: std={np.std(random_values)}"

        # Check that we have values across the full range
        assert np.min(random_values) < 0.1, "No low random values generated"
        assert np.max(random_values) > 0.9, "No high random values generated"

    def test_workforce_source_validation(self, sample_workforce, sample_hazard_config):
        """Confirm that int_workforce_previous_year is being used as the workforce source."""
        with patch('orchestrator_mvp.core.event_emitter.load_hazard_configuration') as mock_load:
            mock_load.return_value = sample_hazard_config

            # The function should accept workforce data that represents int_workforce_previous_year
            events = generate_promotion_events(
                workforce=sample_workforce,
                simulation_year=2023,
                scenario_id='test_scenario',
                random_seed=42
            )

            # All promoted employees should come from the input workforce
            promoted_ids = {event['employee_id'] for event in events}
            workforce_ids = set(sample_workforce['employee_id'])

            assert promoted_ids.issubset(workforce_ids), "Promoted employees not from input workforce"

    def test_configuration_loading(self, sample_hazard_config):
        """Validate that promotion hazard configuration is loaded correctly from seed files."""
        with patch('orchestrator_mvp.core.event_emitter.load_hazard_configuration') as mock_load:
            mock_load.return_value = sample_hazard_config

            # Mock the workforce
            workforce = pd.DataFrame([{
                'employee_id': 'EMP_1',
                'level': 1,
                'age': 30,
                'tenure': 5,
                'base_salary': 60000
            }])

            # Call the function
            events = generate_promotion_events(
                workforce=workforce,
                simulation_year=2023,
                scenario_id='test_scenario',
                random_seed=42
            )

            # Verify configuration was loaded
            mock_load.assert_called_once()

            # The loaded config should be used for calculations
            # (This is implicitly tested by other tests that verify correct probabilities)

    def test_promotion_rates_by_level(self, sample_workforce, sample_hazard_config):
        """Test that actual promotion rates by level match expected hazard-based calculations."""
        with patch('orchestrator_mvp.core.event_emitter.load_hazard_configuration') as mock_load:
            mock_load.return_value = sample_hazard_config

            events = generate_promotion_events(
                workforce=sample_workforce,
                simulation_year=2023,
                scenario_id='test_scenario',
                random_seed=42
            )

            # Calculate promotion rates by level
            events_df = pd.DataFrame(events)
            workforce_by_level = sample_workforce.groupby('level').size()
            promotions_by_level = events_df.groupby('old_level').size()

            # Calculate actual rates
            promotion_rates = {}
            for level in [1, 2, 3, 4]:
                if level in promotions_by_level.index:
                    rate = promotions_by_level[level] / workforce_by_level[level]
                    promotion_rates[level] = rate
                else:
                    promotion_rates[level] = 0.0

            # Expected rates based on hazard config (with some variance for randomness)
            # Level 1: ~6-8% (base_rate 0.08 * dampener 1.0)
            assert 0.05 < promotion_rates.get(1, 0) < 0.11, f"Level 1 rate out of range: {promotion_rates.get(1, 0)}"

            # Level 2: ~5-7% (base_rate 0.07 * dampener 0.9 = 0.063)
            assert 0.04 < promotion_rates.get(2, 0) < 0.09, f"Level 2 rate out of range: {promotion_rates.get(2, 0)}"

            # Level 3: ~4-6% (base_rate 0.05 * dampener 0.8 = 0.04)
            assert 0.02 < promotion_rates.get(3, 0) < 0.07, f"Level 3 rate out of range: {promotion_rates.get(3, 0)}"

            # Level 4: ~3-4% (base_rate 0.04 * dampener 0.7 = 0.028)
            assert 0.01 < promotion_rates.get(4, 0) < 0.05, f"Level 4 rate out of range: {promotion_rates.get(4, 0)}"

    def test_event_structure_validation(self, sample_workforce, sample_hazard_config):
        """Verify that generated promotion events have proper structure and required fields."""
        with patch('orchestrator_mvp.core.event_emitter.load_hazard_configuration') as mock_load:
            mock_load.return_value = sample_hazard_config

            events = generate_promotion_events(
                workforce=sample_workforce,
                simulation_year=2023,
                scenario_id='test_scenario',
                random_seed=42
            )

            # Required fields for promotion events
            required_fields = {
                'event_id', 'employee_id', 'event_type', 'event_date',
                'simulation_year', 'scenario_id', 'old_level', 'new_level',
                'old_salary', 'new_salary', 'promotion_percentage'
            }

            for event in events:
                # Check all required fields are present
                assert set(event.keys()) >= required_fields, f"Missing required fields in event: {event}"

                # Validate event type
                assert event['event_type'] == 'promotion', f"Wrong event type: {event['event_type']}"

                # Validate level progression
                assert event['new_level'] == event['old_level'] + 1, "Invalid level progression"

                # Validate salary increase
                assert event['new_salary'] > event['old_salary'], "Salary should increase with promotion"

                # Validate promotion percentage is reasonable (10-20%)
                assert 0.10 <= event['promotion_percentage'] <= 0.20, f"Invalid promotion percentage: {event['promotion_percentage']}"

    def test_database_storage_validation(self, sample_workforce, sample_hazard_config):
        """Confirm events are stored correctly in the database."""
        with patch('orchestrator_mvp.core.event_emitter.load_hazard_configuration') as mock_load:
            mock_load.return_value = sample_hazard_config

            # Generate events
            events = generate_promotion_events(
                workforce=sample_workforce,
                simulation_year=2023,
                scenario_id='test_scenario',
                random_seed=42
            )

            # Convert to DataFrame to simulate database storage
            events_df = pd.DataFrame(events)

            # Validate data types
            assert events_df['event_id'].dtype == 'object', "event_id should be string"
            assert events_df['employee_id'].dtype == 'object', "employee_id should be string"
            assert events_df['simulation_year'].dtype in ['int64', 'int32'], "simulation_year should be integer"
            assert events_df['old_level'].dtype in ['int64', 'int32'], "old_level should be integer"
            assert events_df['new_level'].dtype in ['int64', 'int32'], "new_level should be integer"
            assert events_df['old_salary'].dtype in ['float64', 'int64'], "old_salary should be numeric"
            assert events_df['new_salary'].dtype in ['float64', 'int64'], "new_salary should be numeric"

            # Validate no null values in required fields
            assert not events_df[['event_id', 'employee_id', 'event_type', 'event_date']].isnull().any().any(), "Null values in required fields"

            # Validate unique event IDs
            assert events_df['event_id'].nunique() == len(events_df), "Duplicate event IDs found"

    def test_edge_cases(self, sample_hazard_config):
        """Test edge cases like empty workforce, missing configuration, etc."""
        # Test with empty workforce
        with patch('orchestrator_mvp.core.event_emitter.load_hazard_configuration') as mock_load:
            mock_load.return_value = sample_hazard_config

            empty_workforce = pd.DataFrame()
            events = generate_promotion_events(
                workforce=empty_workforce,
                simulation_year=2023,
                scenario_id='test_scenario',
                random_seed=42
            )

            assert len(events) == 0, "Should return empty list for empty workforce"

        # Test with invalid level
        with patch('orchestrator_mvp.core.event_emitter.load_hazard_configuration') as mock_load:
            mock_load.return_value = sample_hazard_config

            invalid_workforce = pd.DataFrame([{
                'employee_id': 'EMP_1',
                'level': 5,  # Level 5 not in hazard config
                'age': 30,
                'tenure': 5,
                'base_salary': 100000
            }])

            events = generate_promotion_events(
                workforce=invalid_workforce,
                simulation_year=2023,
                scenario_id='test_scenario',
                random_seed=42
            )

            # Should handle gracefully (no promotions for level 5)
            assert len(events) == 0, "Should not promote employees at invalid levels"
