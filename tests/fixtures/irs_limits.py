"""
IRS 402(g) Contribution Limit Fixtures for Property-Based Testing

This module provides test fixtures and helper functions for validating
IRS 402(g) contribution limit compliance in the PlanAlign Engine.

Key Components:
- IRSLimitConfig: Pydantic model for IRS limit configuration
- EmployeeContributionScenario: Test scenario data class
- Hypothesis strategies for generating test data
- Helper functions for contribution calculations
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class IRSLimitConfig(BaseModel):
    """IRS 402(g) limit configuration for a given year.

    Mirrors the structure of config_irs_limits seed file.
    """
    limit_year: int = Field(..., ge=2020, le=2050)
    base_limit: int = Field(..., ge=0, le=100000)
    catch_up_limit: int = Field(..., ge=0, le=150000)
    catch_up_age_threshold: int = Field(..., ge=40, le=70)

    @property
    def effective_limit_for_age(self) -> callable:
        """Returns a function to get the applicable limit for an age."""
        def get_limit(age: int) -> int:
            return self.catch_up_limit if age >= self.catch_up_age_threshold else self.base_limit
        return get_limit


# Default IRS limits for testing (2025 values)
DEFAULT_IRS_LIMITS_2025 = IRSLimitConfig(
    limit_year=2025,
    base_limit=23500,
    catch_up_limit=31000,
    catch_up_age_threshold=50
)

# IRS limits for projection years (based on historical growth patterns)
IRS_LIMITS_BY_YEAR = {
    2025: IRSLimitConfig(limit_year=2025, base_limit=23500, catch_up_limit=31000, catch_up_age_threshold=50),
    2026: IRSLimitConfig(limit_year=2026, base_limit=24000, catch_up_limit=32000, catch_up_age_threshold=50),
    2027: IRSLimitConfig(limit_year=2027, base_limit=24500, catch_up_limit=32500, catch_up_age_threshold=50),
    2028: IRSLimitConfig(limit_year=2028, base_limit=25000, catch_up_limit=33000, catch_up_age_threshold=50),
    2029: IRSLimitConfig(limit_year=2029, base_limit=25500, catch_up_limit=33500, catch_up_age_threshold=50),
    2030: IRSLimitConfig(limit_year=2030, base_limit=26000, catch_up_limit=34000, catch_up_age_threshold=50),
}


@dataclass
class EmployeeContributionScenario:
    """Test scenario for employee contribution calculations.

    Represents a single employee's contribution scenario for testing
    IRS limit compliance.
    """
    employee_id: str
    age: int
    annual_compensation: Decimal
    deferral_rate: Decimal
    plan_year: int

    # Calculated fields (populated by calculate_contributions)
    requested_contribution: Optional[Decimal] = None
    applicable_irs_limit: Optional[int] = None
    actual_contribution: Optional[Decimal] = None
    irs_limit_applied: Optional[bool] = None
    amount_capped: Optional[Decimal] = None

    def calculate_contributions(self, irs_limits: IRSLimitConfig) -> 'EmployeeContributionScenario':
        """Calculate contribution amounts and IRS limit application.

        This mirrors the logic in int_employee_contributions.sql:
        - requested_contribution = compensation * deferral_rate
        - applicable_irs_limit = catch_up_limit if age >= threshold else base_limit
        - actual_contribution = LEAST(requested, applicable_limit)
        - irs_limit_applied = requested > applicable_limit
        - amount_capped = GREATEST(0, requested - actual)
        """
        self.requested_contribution = self.annual_compensation * self.deferral_rate

        # Determine applicable limit based on age
        if self.age >= irs_limits.catch_up_age_threshold:
            self.applicable_irs_limit = irs_limits.catch_up_limit
        else:
            self.applicable_irs_limit = irs_limits.base_limit

        # Apply IRS limit using LEAST pattern
        self.actual_contribution = min(
            self.requested_contribution,
            Decimal(self.applicable_irs_limit)
        )

        # Set limit applied flag
        self.irs_limit_applied = self.requested_contribution > Decimal(self.applicable_irs_limit)

        # Calculate amount capped off
        self.amount_capped = max(
            Decimal(0),
            self.requested_contribution - self.actual_contribution
        )

        return self


def get_irs_limits_for_year(year: int) -> IRSLimitConfig:
    """Get IRS limits for a given year with fallback to nearest available year.

    Mirrors the fallback logic in int_employee_contributions.sql.
    """
    if year in IRS_LIMITS_BY_YEAR:
        return IRS_LIMITS_BY_YEAR[year]

    # Fallback to nearest available year
    available_years = sorted(IRS_LIMITS_BY_YEAR.keys())
    nearest_year = min(available_years, key=lambda y: abs(y - year))
    return IRS_LIMITS_BY_YEAR[nearest_year]


def calculate_max_contribution(
    age: int,
    compensation: Decimal,
    deferral_rate: Decimal,
    irs_limits: IRSLimitConfig
) -> Decimal:
    """Calculate the maximum allowed contribution for an employee.

    This is the core IRS compliance function that ensures no contribution
    exceeds the applicable IRS 402(g) limit.

    Args:
        age: Employee's age as of December 31 of the plan year
        compensation: Annual compensation (may be prorated)
        deferral_rate: Employee's elected deferral rate (0.0 to 1.0)
        irs_limits: IRS limit configuration for the plan year

    Returns:
        Maximum allowed contribution amount (capped at IRS limit)
    """
    requested = compensation * deferral_rate

    applicable_limit = (
        irs_limits.catch_up_limit
        if age >= irs_limits.catch_up_age_threshold
        else irs_limits.base_limit
    )

    return min(requested, Decimal(applicable_limit))


def is_contribution_compliant(
    contribution_amount: Decimal,
    age: int,
    irs_limits: IRSLimitConfig
) -> bool:
    """Check if a contribution amount is IRS 402(g) compliant.

    Args:
        contribution_amount: The actual contribution amount
        age: Employee's age as of December 31 of the plan year
        irs_limits: IRS limit configuration for the plan year

    Returns:
        True if contribution is within IRS limits, False otherwise
    """
    applicable_limit = (
        irs_limits.catch_up_limit
        if age >= irs_limits.catch_up_age_threshold
        else irs_limits.base_limit
    )

    return contribution_amount <= Decimal(applicable_limit)
