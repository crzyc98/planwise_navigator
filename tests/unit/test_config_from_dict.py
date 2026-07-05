"""Test SimulationConfig.from_dict() robustness with key filtering.

This module tests that from_dict() gracefully handles config dicts with
unknown keys (from scenario overrides) and missing optional fields.
"""

import pytest
from pydantic import ValidationError
from planalign_core.schema import SimulationConfig


class TestFromDictRobustness:
    """Test that from_dict() handles various dict shapes gracefully."""

    def test_from_dict_with_all_valid_fields(self):
        """Test basic case: all valid fields specified."""
        config_dict = {
            "start_year": 2025,
            "end_year": 2026,
            "random_seed": 42,
            "target_growth_rate": 0.03,
            "total_termination_rate": 0.12,
        }

        # Should succeed without filtering needed
        config = SimulationConfig.from_dict(config_dict)
        assert config.start_year == 2025
        assert config.end_year == 2026
        assert config.random_seed == 42

    def test_from_dict_filters_unknown_keys(self):
        """Test that unknown keys are silently filtered.

        This is the core feature of the fix - robust deserialization
        for config dicts that may contain extra keys from Studio overrides.
        """
        config_dict = {
            "start_year": 2025,
            "end_year": 2026,
            "random_seed": 42,
            "unknown_field_1": "should_be_ignored",
            "unknown_field_2": 999,
            "extra_scenario_override": {"some": "data"},
            "ui_settings": {"key": "value"},
        }

        # Should succeed - unknown keys filtered silently
        config = SimulationConfig.from_dict(config_dict)
        assert config.start_year == 2025
        assert config.end_year == 2026
        # Unknown fields should not be accessible
        assert not hasattr(config, "unknown_field_1")
        assert not hasattr(config, "ui_settings")

    def test_from_dict_with_missing_optional_fields(self):
        """Test that missing optional fields use Pydantic defaults."""
        config_dict = {
            "start_year": 2025,
            "end_year": 2026,
            # Missing: random_seed, cola_rate, merit_budget_pct, etc.
        }

        # Should succeed using Pydantic defaults
        config = SimulationConfig.from_dict(config_dict)
        assert config.start_year == 2025
        assert config.random_seed == 42  # Default value
        assert config.cola_rate == 0.025  # Default value
        assert config.target_growth_rate == 0.03  # Default value

    def test_from_dict_with_missing_required_field_raises_error(self):
        """Test that missing required fields raise ValidationError."""
        config_dict = {
            "start_year": 2025,
            # Missing: end_year (required)
        }

        # Should raise ValidationError
        with pytest.raises(ValidationError):
            SimulationConfig.from_dict(config_dict)

    def test_from_dict_preserves_all_field_values(self):
        """Test that filtering doesn't corrupt valid field values."""
        config_dict = {
            "start_year": 2024,
            "end_year": 2027,
            "random_seed": 123,
            "target_growth_rate": 0.05,
            "total_termination_rate": 0.15,
            "new_hire_termination_rate": 0.30,
            "promotion_budget_pct": 0.20,
            "cola_rate": 0.03,
            "merit_budget_pct": 0.05,
            "promotion_increase_pct": 0.20,
            "unknown_key": "ignored",  # Extra key to filter
        }

        config = SimulationConfig.from_dict(config_dict)

        # All specified values should be preserved
        assert config.start_year == 2024
        assert config.end_year == 2027
        assert config.random_seed == 123
        assert config.target_growth_rate == 0.05
        assert config.total_termination_rate == 0.15
        assert config.new_hire_termination_rate == 0.30
        assert config.promotion_budget_pct == 0.20
        assert config.cola_rate == 0.03
        assert config.merit_budget_pct == 0.05
        assert config.promotion_increase_pct == 0.20

    def test_from_dict_with_invalid_type_raises_error(self):
        """Test that invalid field types are rejected."""
        config_dict = {
            "start_year": [2025],  # List instead of int (non-coercible)
            "end_year": 2026,
        }

        # Should raise ValidationError for type mismatch
        with pytest.raises(ValidationError):
            SimulationConfig.from_dict(config_dict)

    def test_from_dict_with_out_of_range_value_raises_error(self):
        """Test that out-of-range values are rejected."""
        config_dict = {
            "start_year": 1900,  # Before minimum (2020)
            "end_year": 2026,
        }

        # Should raise ValidationError for range violation
        with pytest.raises(ValidationError):
            SimulationConfig.from_dict(config_dict)

    def test_from_dict_with_invalid_cross_field_validation(self):
        """Test that cross-field validators are applied."""
        config_dict = {
            "start_year": 2025,
            "end_year": 2020,  # Invalid: must be > start_year
        }

        # Should raise ValidationError from cross-field validator
        with pytest.raises(ValidationError):
            SimulationConfig.from_dict(config_dict)

    def test_from_dict_with_studio_scenario_override(self):
        """Test realistic scenario: base config + Studio overrides.

        Simulates the actual use case from result_handlers.py where
        base config is merged with scenario-specific overrides.
        """
        # Simulate base config
        base_config = {
            "start_year": 2025,
            "end_year": 2027,
            "target_growth_rate": 0.03,
        }

        # Simulate Studio scenario override
        scenario_override = {
            "target_growth_rate": 0.05,  # Override
            "random_seed": 999,
            "scenario_name": "high_growth",  # Extra field from Studio
            "scenario_description": "Test scenario",  # Extra field
            "ui_state": {"expanded": True},  # Extra field
        }

        # Merge (simulating result_handlers.py behavior)
        merged = {**base_config, **scenario_override}

        # Should survive deserialization despite extra keys
        config = SimulationConfig.from_dict(merged)

        assert config.start_year == 2025
        assert config.end_year == 2027
        assert config.target_growth_rate == 0.05  # Override applied
        assert config.random_seed == 999
        # Extra fields should not be accessible
        assert not hasattr(config, "scenario_name")
        assert not hasattr(config, "ui_state")
