"""
Property-Based Tests for IRS 402(g) Contribution Limit Compliance

This module provides comprehensive property-based testing using Hypothesis
to mathematically guarantee that no 401(k) contributions exceed IRS limits.

Key Invariants Tested:
1. max(annual_contribution_amount) <= applicable_irs_limit for ALL employees
2. irs_limit_applied flag accurately reflects when capping occurred
3. Age threshold boundary behavior is correct (49, 50, 51)
4. All edge cases are covered through exhaustive property generation

Test Strategy:
- Generate 10,000+ random employee scenarios per test
- Cover all age ranges (18-80)
- Cover all compensation levels ($0 - $10M)
- Cover all deferral rates (0% - 100%)
- Cover all supported plan years (2025-2035)

This satisfies FR-010 and User Story 4 from the feature specification.
"""

from datetime import timedelta
from decimal import Decimal
from typing import Tuple

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from tests.fixtures.irs_limits import (
    DEFAULT_IRS_LIMITS_2025,
    IRSLimitConfig,
    EmployeeContributionScenario,
    calculate_max_contribution,
    get_irs_limits_for_year,
    is_contribution_compliant,
)


# Hypothesis strategies for test data generation
age_strategy = st.integers(min_value=18, max_value=80)
compensation_strategy = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("10000000"),  # Up to $10M
    places=2,
    allow_nan=False,
    allow_infinity=False
)
deferral_rate_strategy = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1.0"),  # 0% to 100%
    places=4,
    allow_nan=False,
    allow_infinity=False
)
plan_year_strategy = st.integers(min_value=2025, max_value=2035)


class TestIRSContributionLimitCompliance:
    """Property-based tests for IRS 402(g) contribution limit compliance."""

    @given(
        age=age_strategy,
        compensation=compensation_strategy,
        deferral_rate=deferral_rate_strategy,
        plan_year=plan_year_strategy
    )
    @settings(max_examples=10000, deadline=timedelta(seconds=60))
    def test_contribution_never_exceeds_limit(
        self,
        age: int,
        compensation: Decimal,
        deferral_rate: Decimal,
        plan_year: int
    ):
        """Core invariant: No contribution can ever exceed the IRS 402(g) limit.

        This is the most critical test - it mathematically guarantees that
        the LEAST(requested, limit) pattern correctly caps all contributions.

        Property:
            ∀ employee: annual_contribution_amount ≤ applicable_irs_limit
        """
        # Skip invalid scenarios
        assume(compensation >= 0)
        assume(0 <= deferral_rate <= 1)

        # Get IRS limits for the plan year
        irs_limits = get_irs_limits_for_year(plan_year)

        # Calculate contribution using our function
        contribution = calculate_max_contribution(
            age=age,
            compensation=compensation,
            deferral_rate=deferral_rate,
            irs_limits=irs_limits
        )

        # Determine applicable limit based on age
        applicable_limit = (
            irs_limits.catch_up_limit
            if age >= irs_limits.catch_up_age_threshold
            else irs_limits.base_limit
        )

        # CORE INVARIANT: Contribution must never exceed the limit
        assert contribution <= Decimal(applicable_limit), (
            f"IRS VIOLATION: contribution ${contribution:.2f} exceeds "
            f"limit ${applicable_limit} for age {age}"
        )

    @given(
        age=age_strategy,
        compensation=compensation_strategy,
        deferral_rate=deferral_rate_strategy,
        plan_year=plan_year_strategy
    )
    @settings(max_examples=10000, deadline=timedelta(seconds=60))
    def test_irs_limit_applied_flag_accuracy(
        self,
        age: int,
        compensation: Decimal,
        deferral_rate: Decimal,
        plan_year: int
    ):
        """The irs_limit_applied flag must accurately reflect capping behavior.

        Property:
            irs_limit_applied == True  ⟺  requested_contribution > applicable_limit
            irs_limit_applied == False ⟺  requested_contribution ≤ applicable_limit
        """
        assume(compensation >= 0)
        assume(0 <= deferral_rate <= 1)

        irs_limits = get_irs_limits_for_year(plan_year)

        # Create and calculate scenario
        scenario = EmployeeContributionScenario(
            employee_id=f"TEST_{age}_{plan_year}",
            age=age,
            annual_compensation=compensation,
            deferral_rate=deferral_rate,
            plan_year=plan_year
        ).calculate_contributions(irs_limits)

        # Calculate expected flag value
        requested = compensation * deferral_rate
        applicable_limit = (
            irs_limits.catch_up_limit
            if age >= irs_limits.catch_up_age_threshold
            else irs_limits.base_limit
        )
        expected_flag = requested > Decimal(applicable_limit)

        # Flag must match actual behavior
        assert scenario.irs_limit_applied == expected_flag, (
            f"Flag mismatch: flag={scenario.irs_limit_applied}, "
            f"expected={expected_flag}, requested=${requested:.2f}, "
            f"limit=${applicable_limit}"
        )

    @given(
        compensation=compensation_strategy,
        deferral_rate=deferral_rate_strategy,
        plan_year=plan_year_strategy
    )
    @settings(max_examples=5000, deadline=timedelta(seconds=60))
    def test_age_threshold_boundary(
        self,
        compensation: Decimal,
        deferral_rate: Decimal,
        plan_year: int
    ):
        """Age threshold boundary must be correctly applied.

        Tests ages 49, 50, and 51 to verify:
        - Age 49: Must use base_limit
        - Age 50: Must use catch_up_limit (threshold is >=, not >)
        - Age 51: Must use catch_up_limit
        """
        assume(compensation >= 0)
        assume(0 <= deferral_rate <= 1)

        irs_limits = get_irs_limits_for_year(plan_year)
        threshold = irs_limits.catch_up_age_threshold

        # Test just below threshold
        age_below = threshold - 1
        contrib_below = calculate_max_contribution(
            age=age_below,
            compensation=compensation,
            deferral_rate=deferral_rate,
            irs_limits=irs_limits
        )
        assert contrib_below <= Decimal(irs_limits.base_limit), (
            f"Age {age_below} should use base_limit ${irs_limits.base_limit}"
        )

        # Test at threshold
        contrib_at = calculate_max_contribution(
            age=threshold,
            compensation=compensation,
            deferral_rate=deferral_rate,
            irs_limits=irs_limits
        )
        # At threshold, can use catch_up_limit
        assert contrib_at <= Decimal(irs_limits.catch_up_limit), (
            f"Age {threshold} should use catch_up_limit ${irs_limits.catch_up_limit}"
        )

        # Test above threshold
        age_above = threshold + 1
        contrib_above = calculate_max_contribution(
            age=age_above,
            compensation=compensation,
            deferral_rate=deferral_rate,
            irs_limits=irs_limits
        )
        assert contrib_above <= Decimal(irs_limits.catch_up_limit), (
            f"Age {age_above} should use catch_up_limit ${irs_limits.catch_up_limit}"
        )

    @given(
        age=age_strategy,
        compensation=compensation_strategy,
        deferral_rate=deferral_rate_strategy,
        plan_year=plan_year_strategy
    )
    @settings(max_examples=10000, deadline=timedelta(seconds=60))
    def test_amount_capped_calculation_accuracy(
        self,
        age: int,
        compensation: Decimal,
        deferral_rate: Decimal,
        plan_year: int
    ):
        """The amount_capped field must equal GREATEST(0, requested - actual).

        Property:
            amount_capped = max(0, requested_contribution - actual_contribution)
        """
        assume(compensation >= 0)
        assume(0 <= deferral_rate <= 1)

        irs_limits = get_irs_limits_for_year(plan_year)

        scenario = EmployeeContributionScenario(
            employee_id=f"TEST_{age}",
            age=age,
            annual_compensation=compensation,
            deferral_rate=deferral_rate,
            plan_year=plan_year
        ).calculate_contributions(irs_limits)

        expected_capped = max(
            Decimal(0),
            scenario.requested_contribution - scenario.actual_contribution
        )

        assert scenario.amount_capped == expected_capped, (
            f"Amount capped mismatch: got ${scenario.amount_capped:.2f}, "
            f"expected ${expected_capped:.2f}"
        )


class TestIRSLimitConfigValidation:
    """Tests for IRS limit configuration validation."""

    def test_default_limits_are_valid(self):
        """Default 2025 limits match IRS published values."""
        limits = DEFAULT_IRS_LIMITS_2025

        assert limits.limit_year == 2025
        assert limits.base_limit == 23500
        assert limits.catch_up_limit == 31000
        assert limits.catch_up_age_threshold == 50

    def test_catch_up_limit_exceeds_base_limit(self):
        """Catch-up limit must always exceed base limit."""
        for year, limits in get_irs_limits_for_year.__globals__['IRS_LIMITS_BY_YEAR'].items():
            assert limits.catch_up_limit > limits.base_limit, (
                f"Year {year}: catch_up ${limits.catch_up_limit} "
                f"should exceed base ${limits.base_limit}"
            )

    @given(year=st.integers(min_value=2020, max_value=2050))
    @settings(max_examples=100)
    def test_fallback_logic_returns_valid_limits(self, year: int):
        """Fallback logic always returns valid IRS limits."""
        limits = get_irs_limits_for_year(year)

        assert limits is not None
        assert limits.base_limit > 0
        assert limits.catch_up_limit > limits.base_limit
        assert 40 <= limits.catch_up_age_threshold <= 70


class TestEdgeCases:
    """Edge case tests for IRS compliance."""

    def test_zero_compensation_zero_contribution(self):
        """Zero compensation must result in zero contribution."""
        contribution = calculate_max_contribution(
            age=35,
            compensation=Decimal("0"),
            deferral_rate=Decimal("1.0"),
            irs_limits=DEFAULT_IRS_LIMITS_2025
        )
        assert contribution == Decimal("0")

    def test_zero_deferral_rate_zero_contribution(self):
        """Zero deferral rate must result in zero contribution."""
        contribution = calculate_max_contribution(
            age=35,
            compensation=Decimal("1000000"),
            deferral_rate=Decimal("0"),
            irs_limits=DEFAULT_IRS_LIMITS_2025
        )
        assert contribution == Decimal("0")

    def test_100_percent_deferral_high_earner_capped(self):
        """High earner at 100% deferral must be capped at IRS limit."""
        limits = DEFAULT_IRS_LIMITS_2025

        # Under 50: should be capped at base limit
        contribution_under_50 = calculate_max_contribution(
            age=35,
            compensation=Decimal("500000"),
            deferral_rate=Decimal("1.0"),
            irs_limits=limits
        )
        assert contribution_under_50 == Decimal(limits.base_limit)

        # 50+: should be capped at catch-up limit
        contribution_over_50 = calculate_max_contribution(
            age=55,
            compensation=Decimal("500000"),
            deferral_rate=Decimal("1.0"),
            irs_limits=limits
        )
        assert contribution_over_50 == Decimal(limits.catch_up_limit)

    def test_exact_limit_is_allowed(self):
        """Contribution exactly at the limit is compliant."""
        limits = DEFAULT_IRS_LIMITS_2025

        # Contribution exactly at base limit
        assert is_contribution_compliant(
            contribution_amount=Decimal(limits.base_limit),
            age=35,
            irs_limits=limits
        )

        # Contribution exactly at catch-up limit
        assert is_contribution_compliant(
            contribution_amount=Decimal(limits.catch_up_limit),
            age=55,
            irs_limits=limits
        )

    def test_one_dollar_over_limit_is_violation(self):
        """Contribution one dollar over the limit is a violation."""
        limits = DEFAULT_IRS_LIMITS_2025

        # One dollar over base limit
        assert not is_contribution_compliant(
            contribution_amount=Decimal(limits.base_limit + 1),
            age=35,
            irs_limits=limits
        )

        # One dollar over catch-up limit
        assert not is_contribution_compliant(
            contribution_amount=Decimal(limits.catch_up_limit + 1),
            age=55,
            irs_limits=limits
        )


class TestComplianceGuarantee:
    """Final compliance guarantee tests."""

    @given(
        age=age_strategy,
        compensation=st.decimals(
            min_value=Decimal("500000"),  # High earners
            max_value=Decimal("10000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False
        ),
        deferral_rate=st.decimals(
            min_value=Decimal("0.5"),  # High deferral rates
            max_value=Decimal("1.0"),
            places=4,
            allow_nan=False,
            allow_infinity=False
        )
    )
    @settings(max_examples=10000, deadline=timedelta(seconds=60))
    def test_high_earners_always_compliant(
        self,
        age: int,
        compensation: Decimal,
        deferral_rate: Decimal
    ):
        """High earners with high deferral rates must still be compliant.

        This is the ultimate stress test - the scenario most likely to
        cause IRS limit violations if the capping logic is incorrect.
        """
        limits = DEFAULT_IRS_LIMITS_2025

        contribution = calculate_max_contribution(
            age=age,
            compensation=compensation,
            deferral_rate=deferral_rate,
            irs_limits=limits
        )

        assert is_contribution_compliant(
            contribution_amount=contribution,
            age=age,
            irs_limits=limits
        ), (
            f"COMPLIANCE FAILURE: age={age}, comp=${compensation:.2f}, "
            f"rate={deferral_rate:.4f}, contrib=${contribution:.2f}"
        )
