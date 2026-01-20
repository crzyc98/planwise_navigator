"""
Test fixtures for tenure calculation validation.

This module provides edge case hire dates and expected tenure values
for validating the tenure calculation formula:
    tenure = floor((as_of_date - hire_date) / 365.25)

Feature: 020-fix-tenure-calculation
"""

from datetime import date
from decimal import Decimal
from typing import NamedTuple


class TenureTestCase(NamedTuple):
    """A test case for tenure calculation."""
    name: str
    hire_date: date
    simulation_year: int
    expected_tenure: int
    description: str


# Standard test cases from spec.md acceptance scenarios
SPEC_ACCEPTANCE_CASES = [
    TenureTestCase(
        name="mid_year_hire_2020",
        hire_date=date(2020, 6, 15),
        simulation_year=2025,
        expected_tenure=5,
        description="Given employee hired on 2020-06-15, simulation year 2025, tenure = floor(2025 days / 365.25) = 5"
    ),
    TenureTestCase(
        name="mid_year_hire_same_year",
        hire_date=date(2025, 7, 1),
        simulation_year=2025,
        expected_tenure=0,
        description="Given employee hired on 2025-07-01, simulation year 2025, tenure = floor(183 days / 365.25) = 0"
    ),
    TenureTestCase(
        name="jan_first_hire",
        hire_date=date(2021, 1, 1),
        simulation_year=2025,
        expected_tenure=4,
        description="Given employee hired on 2021-01-01, simulation year 2025, tenure = floor(1826 days / 365.25) = 4"
    ),
]

# Edge cases for boundary conditions
EDGE_CASES = [
    TenureTestCase(
        name="hire_date_equals_year_end",
        hire_date=date(2025, 12, 31),
        simulation_year=2025,
        expected_tenure=0,
        description="Hired exactly on simulation year end date"
    ),
    TenureTestCase(
        name="hire_date_after_year_end",
        hire_date=date(2026, 1, 15),
        simulation_year=2025,
        expected_tenure=0,
        description="Future hire (hire_date > simulation year end) should return 0"
    ),
    TenureTestCase(
        name="leap_year_hire",
        hire_date=date(2020, 2, 29),
        simulation_year=2025,
        expected_tenure=5,
        description="Hired on leap day, verifies 365.25 divisor handles leap years correctly"
    ),
    TenureTestCase(
        name="one_day_before_year",
        hire_date=date(2024, 12, 31),
        simulation_year=2025,
        expected_tenure=0,
        description="Hired one day before simulation year, tenure = floor(365 days / 365.25) = 0 (not quite a full year)"
    ),
    TenureTestCase(
        name="very_long_tenure",
        hire_date=date(1980, 1, 1),
        simulation_year=2025,
        expected_tenure=45,
        description="Long-tenured employee (45+ years)"
    ),
    TenureTestCase(
        name="new_hire_december",
        hire_date=date(2025, 12, 1),
        simulation_year=2025,
        expected_tenure=0,
        description="December hire in simulation year, 30 days tenure = 0 years"
    ),
]

# Year-over-year increment test cases
YEAR_OVER_YEAR_CASES = [
    # Same employee across multiple years should increment by 1
    (
        TenureTestCase(
            name="yoy_base_year",
            hire_date=date(2020, 6, 15),
            simulation_year=2025,
            expected_tenure=5,
            description="Base year tenure"
        ),
        TenureTestCase(
            name="yoy_next_year",
            hire_date=date(2020, 6, 15),
            simulation_year=2026,
            expected_tenure=6,
            description="Next year should increment by 1"
        ),
    ),
    (
        TenureTestCase(
            name="yoy_jan_first_base",
            hire_date=date(2021, 1, 1),
            simulation_year=2025,
            expected_tenure=4,
            description="Jan 1 hire base year"
        ),
        TenureTestCase(
            name="yoy_jan_first_next",
            hire_date=date(2021, 1, 1),
            simulation_year=2026,
            expected_tenure=5,
            description="Jan 1 hire next year should increment by 1"
        ),
    ),
]

# All test cases combined
ALL_TEST_CASES = SPEC_ACCEPTANCE_CASES + EDGE_CASES


def calculate_expected_tenure(hire_date: date, simulation_year: int) -> int:
    """
    Calculate expected tenure using the reference formula.

    Formula: floor((simulation_year_end_date - hire_date) / 365.25)

    Args:
        hire_date: Employee's hire date
        simulation_year: The simulation year

    Returns:
        Integer years of service (truncated, not rounded)
    """
    import math

    if hire_date is None:
        return 0

    year_end = date(simulation_year, 12, 31)

    if hire_date > year_end:
        return 0

    days = (year_end - hire_date).days
    return int(math.floor(days / 365.25))


def get_tenure_band(tenure: int) -> str:
    """
    Get tenure band based on [min, max) interval convention.

    Args:
        tenure: Years of service

    Returns:
        Tenure band label
    """
    if tenure < 2:
        return "< 2"
    elif tenure < 5:
        return "2-4"
    elif tenure < 10:
        return "5-9"
    elif tenure < 20:
        return "10-19"
    else:
        return "20+"
