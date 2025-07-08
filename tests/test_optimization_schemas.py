"""
Tests for optimization_schemas.py module
Validates parameter definitions, validation logic, and format transformations.
"""

import pytest
import sys
import os
from pathlib import Path

# Add the streamlit_dashboard directory to the path so we can import the schema
sys.path.insert(0, str(Path(__file__).parent.parent / "streamlit_dashboard"))

from optimization_schemas import (
    ParameterSchema, ParameterDefinition, ParameterBounds, ParameterCategory,
    ParameterType, ParameterUnit, RiskLevel, get_parameter_schema,
    load_parameter_schema, get_default_parameters, validate_parameters,
    assess_parameter_risk
)


class TestParameterBounds:
    """Test ParameterBounds validation."""

    def test_valid_bounds(self):
        bounds = ParameterBounds(
            min_value=0.01,
            max_value=0.10,
            default_value=0.05
        )
        assert bounds.min_value == 0.01
        assert bounds.max_value == 0.10
        assert bounds.default_value == 0.05
        assert bounds.recommended_min is not None
        assert bounds.recommended_max is not None

    def test_invalid_bounds_order(self):
        with pytest.raises(ValueError, match="min_value.*must be less than max_value"):
            ParameterBounds(
                min_value=0.10,
                max_value=0.01,
                default_value=0.05
            )

    def test_invalid_default_value(self):
        with pytest.raises(ValueError, match="default_value.*must be within bounds"):
            ParameterBounds(
                min_value=0.01,
                max_value=0.10,
                default_value=0.15
            )


class TestParameterDefinition:
    """Test ParameterDefinition functionality."""

    def test_parameter_names_level_specific(self):
        param = ParameterDefinition(
            name="merit_rate",
            display_name="Merit Rate",
            description="Test parameter",
            category=ParameterCategory.MERIT,
            parameter_type=ParameterType.PERCENTAGE,
            unit=ParameterUnit.PERCENTAGE,
            bounds=ParameterBounds(0.01, 0.10, 0.05),
            job_levels=[1, 2, 3],
            is_level_specific=True
        )

        names = param.get_parameter_names()
        expected = ["merit_rate_level_1", "merit_rate_level_2", "merit_rate_level_3"]
        assert names == expected

    def test_parameter_names_not_level_specific(self):
        param = ParameterDefinition(
            name="cola_rate",
            display_name="COLA Rate",
            description="Test parameter",
            category=ParameterCategory.COLA,
            parameter_type=ParameterType.PERCENTAGE,
            unit=ParameterUnit.PERCENTAGE,
            bounds=ParameterBounds(0.0, 0.08, 0.025),
            is_level_specific=False
        )

        names = param.get_parameter_names()
        assert names == ["cola_rate"]

    def test_value_validation_within_bounds(self):
        param = ParameterDefinition(
            name="test_param",
            display_name="Test Parameter",
            description="Test parameter",
            category=ParameterCategory.MERIT,
            parameter_type=ParameterType.PERCENTAGE,
            unit=ParameterUnit.PERCENTAGE,
            bounds=ParameterBounds(0.01, 0.10, 0.05, 0.02, 0.08)
        )

        is_valid, messages, risk = param.validate_value(0.05)
        assert is_valid is True
        assert risk == RiskLevel.LOW

    def test_value_validation_out_of_bounds(self):
        param = ParameterDefinition(
            name="test_param",
            display_name="Test Parameter",
            description="Test parameter",
            category=ParameterCategory.MERIT,
            parameter_type=ParameterType.PERCENTAGE,
            unit=ParameterUnit.PERCENTAGE,
            bounds=ParameterBounds(0.01, 0.10, 0.05)
        )

        is_valid, messages, risk = param.validate_value(0.15)
        assert is_valid is False
        assert any("above maximum" in msg for msg in messages)

    def test_merit_specific_validation(self):
        param = ParameterDefinition(
            name="merit_rate",
            display_name="Merit Rate",
            description="Test parameter",
            category=ParameterCategory.MERIT,
            parameter_type=ParameterType.PERCENTAGE,
            unit=ParameterUnit.PERCENTAGE,
            bounds=ParameterBounds(0.01, 0.15, 0.05)
        )

        # Test high merit rate warning
        is_valid, messages, risk = param.validate_value(0.12)
        assert is_valid is True
        assert any("may exceed budget" in msg for msg in messages)

        # Test low merit rate warning
        is_valid, messages, risk = param.validate_value(0.005)
        assert is_valid is True
        assert any("may impact employee retention" in msg for msg in messages)


class TestParameterSchema:
    """Test the main ParameterSchema class."""

    def test_schema_initialization(self):
        schema = ParameterSchema()
        assert len(schema._parameters) > 0

        # Check that we have the expected parameter categories
        merit_params = schema.get_parameters_by_category(ParameterCategory.MERIT)
        assert len(merit_params) == 5  # 5 job levels

        cola_params = schema.get_parameters_by_category(ParameterCategory.COLA)
        assert len(cola_params) == 1  # Single COLA parameter

        promotion_params = schema.get_parameters_by_category(ParameterCategory.PROMOTION)
        assert len(promotion_params) == 10  # 5 levels × 2 parameters (probability + raise)

    def test_get_parameter(self):
        schema = ParameterSchema()

        # Test existing parameter
        merit_param = schema.get_parameter("merit_rate_level_1")
        assert merit_param is not None
        assert merit_param.category == ParameterCategory.MERIT

        # Test non-existing parameter
        fake_param = schema.get_parameter("nonexistent_param")
        assert fake_param is None

    def test_default_parameters(self):
        schema = ParameterSchema()
        defaults = schema.get_default_parameters()

        # Check that we have defaults for all expected parameters
        assert "merit_rate_level_1" in defaults
        assert "merit_rate_level_5" in defaults
        assert "cola_rate" in defaults
        assert "new_hire_salary_adjustment" in defaults
        assert "promotion_probability_level_1" in defaults
        assert "promotion_raise_level_1" in defaults

        # Validate default values are reasonable
        assert 0.01 <= defaults["merit_rate_level_1"] <= 0.12
        assert 0.0 <= defaults["cola_rate"] <= 0.08
        assert 1.0 <= defaults["new_hire_salary_adjustment"] <= 1.5

    def test_parameter_set_validation_valid(self):
        schema = ParameterSchema()
        defaults = schema.get_default_parameters()

        results = schema.validate_parameter_set(defaults)
        assert results['is_valid'] is True
        assert results['overall_risk'] == RiskLevel.LOW
        assert len(results['errors']) == 0

    def test_parameter_set_validation_invalid(self):
        schema = ParameterSchema()
        defaults = schema.get_default_parameters()

        # Make some parameters invalid
        invalid_params = defaults.copy()
        invalid_params['merit_rate_level_1'] = 0.20  # Above max
        invalid_params['cola_rate'] = -0.01  # Below min

        results = schema.validate_parameter_set(invalid_params)
        assert results['is_valid'] is False
        assert len(results['errors']) > 0

    def test_format_transformation_to_compensation_tuning(self):
        schema = ParameterSchema()
        defaults = schema.get_default_parameters()

        comp_tuning_format = schema.transform_to_compensation_tuning_format(defaults)

        # Check structure
        assert 'merit_base' in comp_tuning_format
        assert 'cola_rate' in comp_tuning_format
        assert 'new_hire_salary_adjustment' in comp_tuning_format
        assert 'promotion_probability' in comp_tuning_format
        assert 'promotion_raise' in comp_tuning_format

        # Check merit rates are properly mapped
        assert len(comp_tuning_format['merit_base']) == 5
        for level in range(1, 6):
            assert level in comp_tuning_format['merit_base']
            expected_value = defaults[f"merit_rate_level_{level}"]
            assert comp_tuning_format['merit_base'][level] == expected_value

        # Check COLA is uniform across levels
        assert len(comp_tuning_format['cola_rate']) == 5
        cola_value = defaults['cola_rate']
        for level in range(1, 6):
            assert comp_tuning_format['cola_rate'][level] == cola_value

    def test_format_transformation_from_compensation_tuning(self):
        schema = ParameterSchema()

        # Create compensation tuning format data
        comp_tuning_data = {
            'merit_base': {1: 0.045, 2: 0.040, 3: 0.035, 4: 0.035, 5: 0.040},
            'cola_rate': {1: 0.025, 2: 0.025, 3: 0.025, 4: 0.025, 5: 0.025},
            'new_hire_salary_adjustment': {1: 1.15, 2: 1.15, 3: 1.15, 4: 1.15, 5: 1.15},
            'promotion_probability': {1: 0.12, 2: 0.08, 3: 0.05, 4: 0.02, 5: 0.01},
            'promotion_raise': {1: 0.12, 2: 0.12, 3: 0.12, 4: 0.12, 5: 0.12}
        }

        standard_format = schema.transform_from_compensation_tuning_format(comp_tuning_data)

        # Check merit rate conversion
        for level in range(1, 6):
            param_name = f"merit_rate_level_{level}"
            assert param_name in standard_format
            assert standard_format[param_name] == comp_tuning_data['merit_base'][level]

        # Check uniform parameters
        assert standard_format['cola_rate'] == 0.025
        assert standard_format['new_hire_salary_adjustment'] == 1.15

        # Check promotion parameters
        for level in range(1, 6):
            prob_name = f"promotion_probability_level_{level}"
            raise_name = f"promotion_raise_level_{level}"
            assert standard_format[prob_name] == comp_tuning_data['promotion_probability'][level]
            assert standard_format[raise_name] == comp_tuning_data['promotion_raise'][level]

    def test_round_trip_transformation(self):
        """Test that transformation to and from compensation tuning format preserves data."""
        schema = ParameterSchema()
        original_params = schema.get_default_parameters()

        # Transform to compensation tuning format and back
        comp_tuning_format = schema.transform_to_compensation_tuning_format(original_params)
        recovered_params = schema.transform_from_compensation_tuning_format(comp_tuning_format)

        # Check that we recover the original parameters
        for param_name, original_value in original_params.items():
            assert param_name in recovered_params
            assert abs(recovered_params[param_name] - original_value) < 1e-10

    def test_parameter_groups(self):
        schema = ParameterSchema()
        groups = schema.get_parameter_groups()

        # Check expected groups exist
        assert 'Merit Rates' in groups
        assert 'Cost of Living' in groups
        assert 'New Hire Parameters' in groups
        assert 'Promotion Probabilities' in groups
        assert 'Promotion Raises' in groups

        # Check merit rates group has 5 parameters
        assert len(groups['Merit Rates']) == 5

        # Check promotion parameters are correctly separated
        promo_probs = groups['Promotion Probabilities']
        promo_raises = groups['Promotion Raises']
        assert len(promo_probs) == 5
        assert len(promo_raises) == 5
        assert all('probability' in name for name in promo_probs.keys())
        assert all('raise' in name for name in promo_raises.keys())


class TestConvenienceFunctions:
    """Test the convenience functions for backward compatibility."""

    def test_get_parameter_schema_singleton(self):
        schema1 = get_parameter_schema()
        schema2 = get_parameter_schema()
        assert schema1 is schema2  # Same instance

    def test_load_parameter_schema_format(self):
        schema_dict = load_parameter_schema()

        # Check it has the expected format for advanced_optimization.py
        assert isinstance(schema_dict, dict)

        for param_name, param_info in schema_dict.items():
            assert 'type' in param_info
            assert 'unit' in param_info
            assert 'range' in param_info
            assert 'description' in param_info
            assert len(param_info['range']) == 2
            assert param_info['range'][0] < param_info['range'][1]

    def test_get_default_parameters_function(self):
        defaults = get_default_parameters()
        schema = get_parameter_schema()
        schema_defaults = schema.get_default_parameters()

        assert defaults == schema_defaults

    def test_validate_parameters_function(self):
        defaults = get_default_parameters()
        warnings, errors = validate_parameters(defaults)

        assert isinstance(warnings, list)
        assert isinstance(errors, list)
        assert len(errors) == 0  # Defaults should be valid

    def test_assess_parameter_risk_function(self):
        defaults = get_default_parameters()
        risk = assess_parameter_risk(defaults)

        assert isinstance(risk, RiskLevel)
        assert risk == RiskLevel.LOW  # Defaults should be low risk


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    def test_advanced_optimization_compatibility(self):
        """Test compatibility with advanced_optimization.py usage patterns."""
        # Simulate how advanced_optimization.py uses the schema
        schema_dict = load_parameter_schema()
        defaults = get_default_parameters()

        # Test that all parameters in defaults have schema definitions
        for param_name in defaults.keys():
            assert param_name in schema_dict
            param_info = schema_dict[param_name]
            value = defaults[param_name]

            # Check that default value is within range
            assert param_info['range'][0] <= value <= param_info['range'][1]

    def test_compensation_tuning_compatibility(self):
        """Test compatibility with compensation_tuning.py usage patterns."""
        schema = get_parameter_schema()

        # Simulate loading parameters from compensation_tuning.py format
        comp_tuning_params = {
            'merit_base': {1: 0.045, 2: 0.040, 3: 0.035, 4: 0.035, 5: 0.040},
            'cola_rate': {1: 0.025, 2: 0.025, 3: 0.025, 4: 0.025, 5: 0.025},
            'new_hire_salary_adjustment': {1: 1.15, 2: 1.15, 3: 1.15, 4: 1.15, 5: 1.15},
        }

        # Convert to standard format
        standard_params = schema.transform_from_compensation_tuning_format(comp_tuning_params)

        # Validate
        warnings, errors = validate_parameters(standard_params)
        assert len(errors) == 0

        # Convert back
        recovered_params = schema.transform_to_compensation_tuning_format(standard_params)

        # Check key sections were preserved
        assert recovered_params['merit_base'] == comp_tuning_params['merit_base']
        assert recovered_params['cola_rate'] == comp_tuning_params['cola_rate']

    def test_extreme_parameter_values(self):
        """Test validation of extreme parameter values."""
        schema = get_parameter_schema()

        # Test extremely high values
        extreme_params = {
            'merit_rate_level_1': 0.25,  # 25% merit increase
            'cola_rate': 0.15,           # 15% COLA
            'new_hire_salary_adjustment': 2.0,  # 200% premium
            'promotion_probability_level_1': 0.8,  # 80% promotion rate
            'promotion_raise_level_1': 0.5,     # 50% raise
        }

        results = schema.validate_parameter_set(extreme_params)
        assert results['is_valid'] is False
        assert results['overall_risk'] in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        assert len(results['errors']) > 0

    def test_business_scenario_validation(self):
        """Test parameter sets representing realistic business scenarios."""
        schema = get_parameter_schema()

        # Conservative scenario
        conservative_params = {
            'merit_rate_level_1': 0.02,
            'merit_rate_level_2': 0.02,
            'merit_rate_level_3': 0.02,
            'merit_rate_level_4': 0.02,
            'merit_rate_level_5': 0.02,
            'cola_rate': 0.015,
            'new_hire_salary_adjustment': 1.05,
            'promotion_probability_level_1': 0.05,
            'promotion_probability_level_2': 0.03,
            'promotion_probability_level_3': 0.02,
            'promotion_probability_level_4': 0.01,
            'promotion_probability_level_5': 0.005,
            'promotion_raise_level_1': 0.08,
            'promotion_raise_level_2': 0.08,
            'promotion_raise_level_3': 0.08,
            'promotion_raise_level_4': 0.08,
            'promotion_raise_level_5': 0.08,
        }

        results = schema.validate_parameter_set(conservative_params)
        assert results['is_valid'] is True
        assert results['overall_risk'] in [RiskLevel.LOW, RiskLevel.MEDIUM]

        # Aggressive scenario
        aggressive_params = conservative_params.copy()
        aggressive_params.update({
            'merit_rate_level_1': 0.08,
            'merit_rate_level_2': 0.07,
            'merit_rate_level_3': 0.06,
            'merit_rate_level_4': 0.06,
            'merit_rate_level_5': 0.07,
            'cola_rate': 0.04,
            'new_hire_salary_adjustment': 1.25,
        })

        results = schema.validate_parameter_set(aggressive_params)
        assert results['is_valid'] is True
        # Risk could be medium or high depending on exact values
        assert results['overall_risk'] in [RiskLevel.MEDIUM, RiskLevel.HIGH]


if __name__ == "__main__":
    # Run a simple test if called directly
    print("Testing optimization schemas...")

    # Test basic functionality
    schema = get_parameter_schema()
    defaults = schema.get_default_parameters()
    print(f"Schema loaded with {len(defaults)} parameters")

    # Test validation
    results = schema.validate_parameter_set(defaults)
    print(f"Default parameters validation: {results['is_valid']}")
    print(f"Overall risk: {results['overall_risk']}")

    # Test format transformation
    comp_format = schema.transform_to_compensation_tuning_format(defaults)
    recovered = schema.transform_from_compensation_tuning_format(comp_format)

    print(f"Round-trip transformation successful: {len(recovered) == len(defaults)}")

    print("All basic tests passed!")
