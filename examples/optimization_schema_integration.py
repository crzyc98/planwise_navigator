"""
Example Integration of Shared Parameter Schema
Demonstrates how both advanced_optimization.py and compensation_tuning.py
can use the unified optimization_schemas.py module.
"""

import sys
from pathlib import Path

# Add the streamlit_dashboard directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "streamlit_dashboard"))

from optimization_schemas import (
    get_parameter_schema, get_default_parameters, load_parameter_schema,
    validate_parameters, assess_parameter_risk, ParameterCategory, RiskLevel
)


def example_advanced_optimization_integration():
    """Example of how advanced_optimization.py can use the shared schema."""
    print("=== Advanced Optimization Integration Example ===")

    # Load schema in the format expected by advanced_optimization.py
    schema_dict = load_parameter_schema()
    defaults = get_default_parameters()

    print(f"Loaded {len(schema_dict)} parameter definitions")
    print(f"Loaded {len(defaults)} default values")

    # Example parameter with bounds checking (as in advanced_optimization.py)
    param_name = "merit_rate_level_1"
    if param_name in schema_dict:
        param_info = schema_dict[param_name]
        print(f"\n{param_name}:")
        print(f"  Type: {param_info['type']}")
        print(f"  Unit: {param_info['unit']}")
        print(f"  Range: {param_info['range']}")
        print(f"  Description: {param_info['description']}")
        print(f"  Default Value: {defaults[param_name]}")

    # Test parameter validation
    test_params = defaults.copy()
    test_params['merit_rate_level_1'] = 0.12  # High but valid value

    warnings, errors = validate_parameters(test_params)
    risk_level = assess_parameter_risk(test_params)

    print(f"\nValidation Results for Test Parameters:")
    print(f"  Errors: {len(errors)}")
    print(f"  Warnings: {len(warnings)}")
    print(f"  Risk Level: {risk_level}")

    if warnings:
        print("  Warning Details:")
        for warning in warnings[:3]:  # Show first 3 warnings
            print(f"    - {warning}")

    return test_params


def example_compensation_tuning_integration():
    """Example of how compensation_tuning.py can use the shared schema."""
    print("\n=== Compensation Tuning Integration Example ===")

    schema = get_parameter_schema()

    # Get parameters in compensation_tuning.py format
    defaults = schema.get_default_parameters()
    comp_tuning_format = schema.transform_to_compensation_tuning_format(defaults)

    print("Parameters in compensation_tuning.py format:")
    for category, values in comp_tuning_format.items():
        print(f"  {category}:")
        for level, value in values.items():
            print(f"    Level {level}: {value:.4f}")

    # Example of parameter modification (as in compensation_tuning.py)
    modified_params = comp_tuning_format.copy()

    # Increase merit rates by 10%
    for level in modified_params['merit_base']:
        modified_params['merit_base'][level] *= 1.1

    # Apply COLA increase
    for level in modified_params['cola_rate']:
        modified_params['cola_rate'][level] = 0.035  # 3.5% COLA

    print("\nModified Parameters:")
    print(f"  Merit rates increased by 10%")
    print(f"  COLA set to 3.5%")

    # Convert back to standard format for validation
    standard_format = schema.transform_from_compensation_tuning_format(modified_params)

    # Validate the modified parameters
    validation_results = schema.validate_parameter_set(standard_format)

    print(f"\nValidation of Modified Parameters:")
    print(f"  Valid: {validation_results['is_valid']}")
    print(f"  Overall Risk: {validation_results['overall_risk']}")
    print(f"  Warnings: {len(validation_results['warnings'])}")
    print(f"  Errors: {len(validation_results['errors'])}")

    if validation_results['warnings']:
        print("  Warning Details:")
        for warning in validation_results['warnings'][:3]:
            print(f"    - {warning}")

    return modified_params


def example_parameter_groups_usage():
    """Example of using parameter groups for UI organization."""
    print("\n=== Parameter Groups Example ===")

    schema = get_parameter_schema()
    groups = schema.get_parameter_groups()

    print("Available Parameter Groups:")
    for group_name, group_params in groups.items():
        print(f"\n{group_name} ({len(group_params)} parameters):")
        for param_name, param_def in group_params.items():
            default_value = param_def.bounds.default_value
            unit = "%" if param_def.unit.value == "percentage" else param_def.unit.value
            print(f"  {param_def.display_name}: {default_value:.3f} {unit}")
            print(f"    Range: [{param_def.bounds.min_value:.3f}, {param_def.bounds.max_value:.3f}]")
            print(f"    {param_def.description}")


def example_risk_assessment():
    """Example of parameter risk assessment."""
    print("\n=== Risk Assessment Example ===")

    schema = get_parameter_schema()

    # Create different risk scenarios
    scenarios = {
        "Conservative": {
            'merit_rate_level_1': 0.025,
            'merit_rate_level_2': 0.025,
            'merit_rate_level_3': 0.025,
            'merit_rate_level_4': 0.025,
            'merit_rate_level_5': 0.025,
            'cola_rate': 0.02,
            'new_hire_salary_adjustment': 1.05,
        },
        "Balanced": {
            'merit_rate_level_1': 0.045,
            'merit_rate_level_2': 0.040,
            'merit_rate_level_3': 0.035,
            'merit_rate_level_4': 0.035,
            'merit_rate_level_5': 0.040,
            'cola_rate': 0.025,
            'new_hire_salary_adjustment': 1.15,
        },
        "Aggressive": {
            'merit_rate_level_1': 0.08,
            'merit_rate_level_2': 0.075,
            'merit_rate_level_3': 0.07,
            'merit_rate_level_4': 0.07,
            'merit_rate_level_5': 0.075,
            'cola_rate': 0.045,
            'new_hire_salary_adjustment': 1.3,
        }
    }

    print("Risk Assessment for Different Scenarios:")
    for scenario_name, partial_params in scenarios.items():
        # Fill in missing parameters with defaults
        defaults = schema.get_default_parameters()
        full_params = defaults.copy()
        full_params.update(partial_params)

        results = schema.validate_parameter_set(full_params)

        print(f"\n{scenario_name} Scenario:")
        print(f"  Overall Risk: {results['overall_risk']}")
        print(f"  Valid: {results['is_valid']}")
        print(f"  Warnings: {len(results['warnings'])}")

        # Show average merit rate for comparison
        merit_rates = [full_params[f'merit_rate_level_{i}'] for i in range(1, 6)]
        avg_merit = sum(merit_rates) / len(merit_rates)
        print(f"  Average Merit Rate: {avg_merit:.1%}")
        print(f"  COLA Rate: {full_params['cola_rate']:.1%}")
        print(f"  New Hire Premium: {full_params['new_hire_salary_adjustment']:.0%}")


def example_business_impact_analysis():
    """Example of business impact analysis using parameter metadata."""
    print("\n=== Business Impact Analysis Example ===")

    schema = get_parameter_schema()

    # Show parameters by business impact
    high_impact_params = []
    for param_name, param_def in schema._parameters.items():
        if any(keyword in param_def.business_impact.lower()
               for keyword in ['cost', 'budget', 'recruitment', 'retention']):
            high_impact_params.append((param_name, param_def))

    print("High Business Impact Parameters:")
    for param_name, param_def in high_impact_params:
        default_val = param_def.bounds.default_value
        unit = "%" if param_def.unit.value == "percentage" else ""
        print(f"\n{param_def.display_name}:")
        print(f"  Current Value: {default_val:.1%}{unit}")
        print(f"  Impact: {param_def.business_impact}")

        # Calculate potential cost impact (simplified example)
        if param_def.category == ParameterCategory.MERIT:
            # Estimate impact: 1% merit increase ≈ $1M annually for 1000 employees
            estimated_impact = (default_val * 100) * 1_000_000
            print(f"  Estimated Annual Cost Impact: ${estimated_impact:,.0f}")


def main():
    """Run all integration examples."""
    print("Optimization Schema Integration Examples")
    print("=" * 50)

    # Run examples
    advanced_params = example_advanced_optimization_integration()
    comp_tuning_params = example_compensation_tuning_integration()
    example_parameter_groups_usage()
    example_risk_assessment()
    example_business_impact_analysis()

    print("\n" + "=" * 50)
    print("Integration examples completed successfully!")
    print("\nKey Benefits of Shared Schema:")
    print("✅ Unified parameter definitions across interfaces")
    print("✅ Consistent validation logic and risk assessment")
    print("✅ Seamless format transformation between systems")
    print("✅ Comprehensive parameter metadata and documentation")
    print("✅ Business impact analysis and scenario planning")


if __name__ == "__main__":
    main()
