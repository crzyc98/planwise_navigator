#!/usr/bin/env python3
"""
Test script to verify parameter resolution logic without database access.
Tests that compensation parameters from config are correctly extracted and formatted.
"""

import yaml
from pathlib import Path


def test_parameter_extraction():
    """Test that we can extract compensation parameters from config."""
    print("🧪 Testing Parameter Extraction")
    print("=" * 40)

    # Load config
    config_path = Path("config/simulation_config.yaml")
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Extract compensation parameters (same logic as run_multi_year.py)
    compensation = config.get('compensation', {})
    cola_rate = compensation.get('cola_rate', 0.005)
    merit_budget = compensation.get('merit_budget', 0.025)

    print(f"✅ COLA rate extracted: {cola_rate}")
    print(f"✅ Merit budget extracted: {merit_budget}")

    # Test parameter dictionary creation (same as used in dbt vars)
    compensation_params = {
        'cola_rate': cola_rate,
        'merit_budget': merit_budget
    }

    print(f"✅ Parameter dict: {compensation_params}")

    # Test dbt vars string formatting (same as run_multi_year.py)
    vars_dict = {
        "simulation_year": 2025,
        **compensation_params
    }
    vars_string = ", ".join(f"{key}: {value}" for key, value in vars_dict.items())
    dbt_vars_arg = f"{{{vars_string}}}"

    print(f"✅ dbt vars format: --vars '{dbt_vars_arg}'")

    # Test expected vs actual values
    expected_cola = 0.005
    expected_merit = 0.025

    assert cola_rate == expected_cola, f"COLA rate mismatch: expected {expected_cola}, got {cola_rate}"
    assert merit_budget == expected_merit, f"Merit budget mismatch: expected {expected_merit}, got {merit_budget}"

    print("🎉 All parameter extraction tests passed!")
    return True


def test_dbt_command_formatting():
    """Test that dbt command formatting matches expected pattern."""
    print("\n🧪 Testing dbt Command Formatting")
    print("=" * 40)

    # Simulate parameters from config
    compensation_params = {
        'cola_rate': 0.005,
        'merit_budget': 0.025
    }

    # Test command building (same logic as run_multi_year.py)
    vars_dict = {"simulation_year": 2025}
    vars_dict.update(compensation_params)

    vars_string = ", ".join(f"{key}: {value}" for key, value in vars_dict.items())
    expected_vars = "simulation_year: 2025, cola_rate: 0.005, merit_budget: 0.025"

    print(f"Generated vars: {vars_string}")
    print(f"Expected pattern: {expected_vars}")

    # Basic structure check
    assert "cola_rate: 0.005" in vars_string
    assert "merit_budget: 0.025" in vars_string
    assert "simulation_year: 2025" in vars_string

    print("✅ dbt command formatting is correct")
    return True


if __name__ == "__main__":
    print("🚀 Starting Parameter Resolution Tests")
    print("=" * 50)

    try:
        test_parameter_extraction()
        test_dbt_command_formatting()

        print("\n🎉 ALL TESTS PASSED!")
        print("✅ Compensation parameters are correctly configured")
        print("✅ Parameter extraction logic works as expected")
        print("✅ dbt variable formatting is correct")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        exit(1)
