"""
Unit Tests for Workforce Calculation Formula Fix

This module contains comprehensive unit tests for the unified net-hire calculation
formula that treats ALL new hires consistently by applying the new hire termination
rate to the total hiring pool. This mathematically correct approach replaces the
previous separated formula that incorrectly treated replacement hires differently.

Test Coverage:
- Basic unified formula validation
- Edge cases and error conditions
- Backward compatibility
- Real-world scenarios
- Regression tests for the specific user issue
"""

import pytest
import math
from typing import Dict, Any

# Import the corrected calculation function
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'orchestrator_mvp'))
from orchestrator_mvp.core.workforce_calculations import calculate_workforce_requirements


class TestWorkforceCalculationFix:
    """Test suite for the unified workforce calculation formula."""

    def test_corrected_formula_basic_case(self):
        """Test the unified formula with basic scenario."""
        result = calculate_workforce_requirements(
            current_workforce=1000,
            target_growth_rate=0.03,
            total_termination_rate=0.12,
            new_hire_termination_rate=0.25
        )

        # Expected: CEIL((120 + 30) / 0.75) = 200 total hires
        # NOT the old separated: 120 replacement + 40 growth = 160
        assert result['experienced_terminations'] == 120
        assert result['growth_amount'] == 30.0
        assert result['replacement_hires'] == 120  # reporting field
        assert result['growth_hires'] == 80  # 200 - 120 = 80 (derived)
        assert result['total_hires_needed'] == 200  # CEIL(150 / 0.75)
        assert result['expected_new_hire_terminations'] == 50  # ROUND(200 * 0.25)
        assert result['net_hiring_impact'] == 150  # 200 - 50

    def test_user_specific_scenario(self):
        """Test the specific scenario reported by the user (5,036 workforce, 3% growth)."""
        result = calculate_workforce_requirements(
            current_workforce=5036,
            target_growth_rate=0.03,
            total_termination_rate=0.12,  # Assuming standard rate
            new_hire_termination_rate=0.25
        )

        # This should produce ~1,009 hires using unified formula
        expected_experienced_terms = math.ceil(5036 * 0.12)  # 605
        expected_growth_amount = 5036 * 0.03  # 151.08
        net_hires_needed = expected_experienced_terms + expected_growth_amount  # 756.08
        expected_total = math.ceil(net_hires_needed / 0.75)  # 1009

        assert result['experienced_terminations'] == expected_experienced_terms
        assert result['growth_amount'] == expected_growth_amount
        assert result['replacement_hires'] == expected_experienced_terms
        assert result['total_hires_needed'] == expected_total

        # Verify this matches the user's expected value
        assert result['total_hires_needed'] == 1009

    def test_replacement_hires_always_equal_experienced_terminations(self):
        """Replacement hires should always equal experienced terminations (reporting field)."""
        test_cases = [
            (1000, 0.10, 0.03, 0.20),
            (5000, 0.15, 0.05, 0.30),
            (500, 0.08, 0.02, 0.25),
        ]

        for workforce, term_rate, growth_rate, new_hire_term_rate in test_cases:
            result = calculate_workforce_requirements(
                workforce, growth_rate, term_rate, new_hire_term_rate
            )

            # replacement_hires is now a derived reporting field, still equals experienced_terminations
            assert result['replacement_hires'] == result['experienced_terminations']

    def test_growth_hires_calculation(self):
        """Growth hires should be properly calculated using unified formula."""
        result = calculate_workforce_requirements(
            current_workforce=1000,
            target_growth_rate=0.05,  # 50 growth needed
            total_termination_rate=0.10,
            new_hire_termination_rate=0.20  # 20% of new hires terminate
        )

        # Unified formula: total_hires = CEIL((100 + 50) / 0.8) = 188
        # Growth hires (derived) = 188 - 100 = 88
        assert result['total_hires_needed'] == 188
        assert result['growth_hires'] == 88  # total - replacement
        assert result['growth_amount'] == 50.0

    def test_zero_growth_scenario(self):
        """Test scenario with zero growth (only replacement hires needed)."""
        result = calculate_workforce_requirements(
            current_workforce=1000,
            target_growth_rate=0.0,
            total_termination_rate=0.12,
            new_hire_termination_rate=0.25
        )

        # Unified formula: CEIL((120 + 0) / 0.75) = 160
        assert result['growth_amount'] == 0.0
        assert result['growth_hires'] == 40  # 160 - 120 = 40 (derived)
        assert result['replacement_hires'] == 120
        assert result['total_hires_needed'] == 160

    def test_high_growth_scenario(self):
        """Test scenario with high growth rate."""
        result = calculate_workforce_requirements(
            current_workforce=1000,
            target_growth_rate=0.15,  # 15% growth
            total_termination_rate=0.10,
            new_hire_termination_rate=0.30
        )

        # Unified formula: CEIL((100 + 150) / 0.7) = 358
        # Growth hires (derived) = 358 - 100 = 258
        assert result['total_hires_needed'] == 358
        assert result['growth_hires'] == 258  # derived field
        assert result['replacement_hires'] == 100

    def test_edge_case_high_new_hire_termination_rate(self):
        """Test with very high new hire termination rate (but < 100%)."""
        result = calculate_workforce_requirements(
            current_workforce=1000,
            target_growth_rate=0.03,
            total_termination_rate=0.12,
            new_hire_termination_rate=0.90  # 90% termination rate
        )

        # Unified formula: CEIL((120 + 30) / 0.1) = 1500
        # Growth hires (derived) = 1500 - 120 = 1380
        assert result['total_hires_needed'] == 1500
        assert result['growth_hires'] == 1380  # derived field
        assert result['replacement_hires'] == 120

    def test_error_on_100_percent_new_hire_termination_rate(self):
        """Should raise error if new hire termination rate is 100% or higher."""
        with pytest.raises(ValueError, match="cannot be 100% or higher"):
            calculate_workforce_requirements(
                current_workforce=1000,
                target_growth_rate=0.03,
                total_termination_rate=0.12,
                new_hire_termination_rate=1.0
            )

        with pytest.raises(ValueError, match="cannot be 100% or higher"):
            calculate_workforce_requirements(
                current_workforce=1000,
                target_growth_rate=0.03,
                total_termination_rate=0.12,
                new_hire_termination_rate=1.1
            )

    def test_error_on_negative_growth(self):
        """Should raise error for negative growth amounts."""
        with pytest.raises(ValueError, match="Growth amount must be positive"):
            calculate_workforce_requirements(
                current_workforce=1000,
                target_growth_rate=-0.05,  # Negative growth
                total_termination_rate=0.12,
                new_hire_termination_rate=0.25
            )

    def test_return_dictionary_structure(self):
        """Test that return dictionary contains all expected fields."""
        result = calculate_workforce_requirements(
            current_workforce=1000,
            target_growth_rate=0.03,
            total_termination_rate=0.12,
            new_hire_termination_rate=0.25
        )

        expected_fields = [
            'current_workforce',
            'experienced_terminations',
            'growth_amount',
            'replacement_hires',
            'growth_hires',
            'total_hires_needed',
            'expected_new_hire_terminations',
            'net_hiring_impact',
            'formula_details'
        ]

        for field in expected_fields:
            assert field in result, f"Missing field: {field}"

    def test_formula_details_structure(self):
        """Test that formula_details contains correct breakdown."""
        result = calculate_workforce_requirements(
            current_workforce=1000,
            target_growth_rate=0.03,
            total_termination_rate=0.12,
            new_hire_termination_rate=0.25
        )

        formula_details = result['formula_details']
        expected_detail_fields = [
            'experienced_formula',
            'growth_formula',
            'net_hires_formula',
            'total_hiring_formula',
            'new_hire_term_formula',
            'replacement_derived',
            'growth_derived'
        ]

        for field in expected_detail_fields:
            assert field in formula_details, f"Missing formula detail: {field}"

    def test_net_hiring_impact_calculation(self):
        """Test that net hiring impact is calculated correctly."""
        result = calculate_workforce_requirements(
            current_workforce=1000,
            target_growth_rate=0.04,
            total_termination_rate=0.10,
            new_hire_termination_rate=0.20
        )

        expected_net_impact = result['total_hires_needed'] - result['expected_new_hire_terminations']
        assert result['net_hiring_impact'] == expected_net_impact

    def test_backward_compatibility_fields(self):
        """Test that existing fields are preserved for backward compatibility."""
        result = calculate_workforce_requirements(
            current_workforce=1000,
            target_growth_rate=0.03,
            total_termination_rate=0.12,
            new_hire_termination_rate=0.25
        )

        # These fields should still exist for backward compatibility
        assert 'current_workforce' in result
        assert 'experienced_terminations' in result
        assert 'growth_amount' in result
        assert 'total_hires_needed' in result
        assert 'expected_new_hire_terminations' in result
        assert 'net_hiring_impact' in result

    def test_multiple_scenarios_regression(self):
        """Regression test against multiple real-world scenarios."""
        scenarios = [
            # (workforce, growth_rate, term_rate, new_hire_term_rate, expected_min_hires)
            (5036, 0.03, 0.12, 0.25, 1000),  # User's specific case
            (10000, 0.05, 0.15, 0.30, 2000),  # Large company
            (1000, 0.10, 0.20, 0.40, 400),   # High growth scenario
            (500, 0.02, 0.08, 0.15, 50),     # Small company
        ]

        for workforce, growth_rate, term_rate, new_hire_term_rate, min_hires in scenarios:
            result = calculate_workforce_requirements(
                workforce, growth_rate, term_rate, new_hire_term_rate
            )

            # Ensure we meet reasonable bounds for unified formula
            assert result['total_hires_needed'] >= min_hires

            # Ensure replacement hires equal experienced terminations
            assert result['replacement_hires'] == result['experienced_terminations']

            # Ensure total equals replacement + growth
            assert result['total_hires_needed'] == (
                result['replacement_hires'] + result['growth_hires']
            )

    def test_comparison_with_old_incorrect_formula(self):
        """Demonstrate the difference between separated and unified formulas."""
        # Test case from the user's scenario
        workforce = 5036
        growth_rate = 0.03
        term_rate = 0.12
        new_hire_term_rate = 0.25

        # NEW UNIFIED FORMULA (current implementation)
        unified_result = calculate_workforce_requirements(
            workforce, growth_rate, term_rate, new_hire_term_rate
        )

        # OLD SEPARATED FORMULA (previous incorrect approach)
        experienced_terms = math.ceil(workforce * term_rate)  # 605
        growth_amount = workforce * growth_rate  # 151.08
        separated_replacement = experienced_terms  # 605
        separated_growth = math.ceil(growth_amount / (1 - new_hire_term_rate))  # 202
        separated_total = separated_replacement + separated_growth  # 807

        # The unified formula should produce MORE hires than the separated approach
        assert unified_result['total_hires_needed'] > separated_total

        # For this specific case, unified should be 1009, separated would be 807
        assert unified_result['total_hires_needed'] == 1009
        assert separated_total == 807
        increase = unified_result['total_hires_needed'] - separated_total
        assert increase == 202  # Should be exactly 202 more hires

    def test_mathematical_consistency(self):
        """Test mathematical consistency across different parameter combinations."""
        test_params = [
            (1000, 0.01, 0.10, 0.15),
            (1000, 0.03, 0.12, 0.25),
            (1000, 0.05, 0.15, 0.30),
            (2000, 0.02, 0.08, 0.20),
            (5000, 0.04, 0.14, 0.28),
        ]

        for workforce, growth_rate, term_rate, new_hire_term_rate in test_params:
            result = calculate_workforce_requirements(
                workforce, growth_rate, term_rate, new_hire_term_rate
            )

            # Mathematical consistency checks
            assert result['total_hires_needed'] >= result['replacement_hires']
            assert result['total_hires_needed'] >= result['growth_hires']
            assert result['replacement_hires'] == result['experienced_terminations']

            # Net hiring should equal target growth (approximately)
            # Net = total_hires - new_hire_terminations - experienced_terminations
            net_new_employees = (
                result['total_hires_needed'] -
                result['expected_new_hire_terminations'] -
                result['experienced_terminations']
            )

            # Should approximately equal growth amount (within rounding)
            expected_growth = result['growth_amount']
            assert abs(net_new_employees - expected_growth) <= 2  # Allow for rounding
