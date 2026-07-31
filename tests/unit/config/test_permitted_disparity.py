"""Table-driven §401(l) permitted-disparity unit coverage."""

from __future__ import annotations

import pytest

from planalign_orchestrator.config.permitted_disparity import (
    min_schedule_rate,
    permitted_disparity_factor,
    resolve_level,
    validate_core_integration,
    wage_base_for,
)


@pytest.mark.parametrize(
    ("level", "wage_base", "expected"),
    [
        (176100, 176100, 0.057),
        (176099, 176100, 0.054),
        (150000, 176100, 0.054),
        (140880, 176100, 0.043),
        (140881, 176100, 0.054),
        (100000, 176100, 0.043),
        (35220, 176100, 0.057),
        (35221, 176100, 0.043),
        (10000, 40000, 0.057),
        (10001, 40000, 0.043),
    ],
)
def test_permitted_disparity_factor_covers_every_band_and_boundary(
    level: int, wage_base: int, expected: float
) -> None:
    assert permitted_disparity_factor(level, wage_base) == expected


def test_permitted_disparity_factor_rejects_level_above_wage_base() -> None:
    with pytest.raises(ValueError, match="above.*taxable wage base"):
        permitted_disparity_factor(176101, 176100)


@pytest.mark.parametrize(
    ("mode", "value", "wage_base", "expected"),
    [
        ("ss_wage_base", None, 176100, 176100),
        ("percent_of_ss_wage_base", 50, 176100, 88050),
        ("percent_of_ss_wage_base", 1, 50, 1),
        ("fixed_dollar", 150000.5, 176100, 150001),
    ],
)
def test_resolve_level_applies_all_modes_and_half_up_rounding(
    mode: str, value: float | None, wage_base: int, expected: int
) -> None:
    assert resolve_level(mode, value, wage_base) == expected


def test_wage_base_for_reads_the_seed_without_a_database() -> None:
    assert wage_base_for(2026) == 184500


def test_wage_base_for_missing_year_has_a_clear_error() -> None:
    with pytest.raises(ValueError, match="Social Security wage base.*2099"):
        wage_base_for(2099)


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({"status": "flat", "contribution_rate": 0.03}, 0.03),
        (
            {
                "status": "graded_by_service",
                "graded_schedule": [
                    {"contribution_rate": 0.03},
                    {"contribution_rate": 0.01},
                ],
            },
            0.01,
        ),
        (
            {
                "status": "points_based",
                "points_schedule": [{"rate": 0.04}, {"rate": 0.02}],
            },
            0.02,
        ),
        (
            {
                "status": "age_banded",
                "age_schedule": [
                    {"contribution_rate": 0.06},
                    {"contribution_rate": 0.03},
                ],
            },
            0.03,
        ),
    ],
)
def test_min_schedule_rate_uses_the_lowest_possible_employee_rate(
    config: dict, expected: float
) -> None:
    assert min_schedule_rate(config) == expected


def test_a_percentage_base_rate_is_rejected_rather_than_validated_against() -> None:
    """A percentage that leaks into a config schedule must not pass silently.

    5.0 read as a fraction is 100x too large, so min(base_rate, factor) would
    always collapse to the factor and the base-rate leg of the §401(l) test
    would stop binding — an illegal disparity would validate clean.
    """
    config = {
        "enabled": True,
        "status": "age_banded",
        "contribution_rate": 0.05,
        "age_schedule": [{"min_age": 0, "max_age": None, "rate": 5.0}],
        "integration": {
            "enabled": True,
            "level_mode": "ss_wage_base",
            "level_value": None,
            "disparity_rate": 0.057,
        },
    }
    with pytest.raises(ValueError, match="not a decimal fraction"):
        validate_core_integration(config, 2026, 2026)


def test_tufts_style_two_band_integrated_design_is_permitted() -> None:
    """Age-banded base rates compose with one disparity rate under §401(l).

    5%/10% below the wage base and 10%/15% above is a uniform 5-point disparity,
    which is legal in both bands: 5% <= min(5% base, 5.7% factor) binds on the
    younger band's base rate, and the older band has more headroom.
    """
    config = {
        "enabled": True,
        "status": "age_banded",
        "contribution_rate": 0.05,
        "age_schedule": [
            {"min_age": 0, "max_age": 40, "contribution_rate": 0.05},
            {"min_age": 40, "max_age": None, "contribution_rate": 0.10},
        ],
        "integration": {
            "enabled": True,
            "level_mode": "ss_wage_base",
            "level_value": None,
            "disparity_rate": 0.05,
        },
    }
    validate_core_integration(config, 2025, 2029)

    # One point more than the younger band's 5% base rate is not permitted,
    # even though the older band could support it.
    config["integration"]["disparity_rate"] = 0.06
    with pytest.raises(ValueError, match="exceeds the maximum permitted"):
        validate_core_integration(config, 2025, 2029)
