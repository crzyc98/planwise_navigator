"""
Service Tier Configuration Test Fixtures

These fixtures provide pre-defined service tier configurations for testing
the graded_by_service core contribution feature.
"""

from typing import Any


def get_two_tier_schedule() -> list[dict[str, Any]]:
    """
    Standard 2-tier service schedule.

    Returns:
        - 0-9 years: 6%
        - 10+ years: 8%
    """
    return [
        {"min_years": 0, "max_years": 10, "rate": 6.0},
        {"min_years": 10, "max_years": None, "rate": 8.0},
    ]


def get_four_tier_schedule() -> list[dict[str, Any]]:
    """
    Complex 4-tier service schedule for advanced testing.

    Returns:
        - 0-2 years: 4%
        - 3-5 years: 5%
        - 6-10 years: 6%
        - 11+ years: 8%
    """
    return [
        {"min_years": 0, "max_years": 3, "rate": 4.0},
        {"min_years": 3, "max_years": 6, "rate": 5.0},
        {"min_years": 6, "max_years": 11, "rate": 6.0},
        {"min_years": 11, "max_years": None, "rate": 8.0},
    ]


def get_three_tier_schedule() -> list[dict[str, Any]]:
    """
    3-tier service schedule.

    Returns:
        - 0-4 years: 3%
        - 5-9 years: 5%
        - 10+ years: 7%
    """
    return [
        {"min_years": 0, "max_years": 5, "rate": 3.0},
        {"min_years": 5, "max_years": 10, "rate": 5.0},
        {"min_years": 10, "max_years": None, "rate": 7.0},
    ]


def get_dbt_vars_for_graded_service(
    schedule: list[dict[str, Any]],
    simulation_year: int = 2025,
) -> dict[str, Any]:
    """
    Generate dbt variables for a graded_by_service configuration.

    Args:
        schedule: List of tier dictionaries with min_years, max_years, rate
        simulation_year: Target simulation year

    Returns:
        Dictionary of dbt variables
    """
    return {
        "simulation_year": simulation_year,
        "employer_core_status": "graded_by_service",
        "employer_core_graded_schedule": schedule,
    }


def get_dbt_vars_for_flat_rate(
    rate: float = 0.08,
    simulation_year: int = 2025,
) -> dict[str, Any]:
    """
    Generate dbt variables for a flat rate configuration.

    Args:
        rate: Flat contribution rate as decimal (e.g., 0.08 for 8%)
        simulation_year: Target simulation year

    Returns:
        Dictionary of dbt variables
    """
    return {
        "simulation_year": simulation_year,
        "employer_core_status": "flat",
        "employer_core_contribution_rate": rate,
    }


# Pre-configured test scenarios
TWO_TIER_VARS = get_dbt_vars_for_graded_service(get_two_tier_schedule())
FOUR_TIER_VARS = get_dbt_vars_for_graded_service(get_four_tier_schedule())
THREE_TIER_VARS = get_dbt_vars_for_graded_service(get_three_tier_schedule())
FLAT_RATE_8_PERCENT = get_dbt_vars_for_flat_rate(0.08)
FLAT_RATE_2_PERCENT = get_dbt_vars_for_flat_rate(0.02)
