"""§401(l) permitted-disparity validation for employer core contributions."""

from __future__ import annotations

import csv
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping

from .workforce import CoreIntegrationSettings


_SEED_PATH = Path(__file__).resolve().parents[2] / "dbt/seeds/config_irs_limits.csv"
_SCHEDULES = {
    "graded_by_service": "graded_schedule",
    "points_based": "points_schedule",
    "age_banded": "age_schedule",
}


def normalize_dc_plan_integration(dc_plan: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a Studio ``dc_plan`` payload to the engine's decimal-rate shape.

    Shared by config validation and dbt-var export so the two cannot diverge. The
    UI carries the disparity rate as a percentage, matching how it carries the flat
    core rate; the engine only ever sees decimal fractions. If validation read the
    decimal key while the UI wrote the percent key, an illegal rate would read as
    0.0 and pass — so both callers must go through here.
    """
    if "core_integration_disparity_rate_percent" in dc_plan:
        disparity_rate = float(dc_plan["core_integration_disparity_rate_percent"]) / 100
    else:
        disparity_rate = float(
            dc_plan.get("core_integration_disparity_rate", 0.0) or 0.0
        )

    level_value = dc_plan.get("core_integration_level_value")
    return {
        "enabled": bool(dc_plan.get("core_integration_enabled", False)),
        "level_mode": str(dc_plan.get("core_integration_level_mode", "ss_wage_base")),
        "level_value": float(level_value) if level_value is not None else None,
        "disparity_rate": disparity_rate,
    }


def wage_base_for(year: int) -> int:
    """Read the Social Security taxable wage base for ``year`` from the seed CSV."""
    with _SEED_PATH.open(newline="") as seed_file:
        for row in csv.DictReader(seed_file):
            if int(row["limit_year"]) == year:
                return int(row["social_security_wage_base"])
    raise ValueError(
        f"Social Security wage base is not available for simulation year {year}."
    )


def _round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def resolve_level(mode: str, value: float | None, wage_base: int) -> int:
    """Resolve an integration level to whole dollars using administration rounding."""
    if mode == "ss_wage_base":
        return wage_base
    if value is None:
        raise ValueError(f"level_value is required when level_mode is {mode}.")
    decimal_value = Decimal(str(value))
    if mode == "percent_of_ss_wage_base":
        return _round_half_up(Decimal(wage_base) * decimal_value / Decimal("100"))
    if mode == "fixed_dollar":
        return _round_half_up(decimal_value)
    raise ValueError(f"Unsupported employer core integration level_mode: {mode}.")


def permitted_disparity_factor(level: int, wage_base: int) -> float:
    """Return the §401(l) safe-harbor disparity factor for a resolved level."""
    if level > wage_base:
        raise ValueError(
            f"Integration level of ${level:,} is above the taxable wage base of ${wage_base:,}."
        )
    if level == wage_base:
        return 0.057
    floor = max(0.2 * wage_base, 10000)
    if level <= floor:
        return 0.057
    if level <= 0.8 * wage_base:
        return 0.043
    return 0.054


def _tier_rate(tier: Mapping[str, Any]) -> float:
    """Return a schedule tier's rate as a decimal fraction.

    Config and Studio payloads spell this ``contribution_rate``; ``rate`` is
    accepted as a decimal alias. The percentage spelling of ``rate`` belongs to
    the dbt-var shape produced by config/export.py and never reaches here —
    ``_assert_decimal_rate`` below fails loudly if one ever does.
    """
    return float(tier.get("contribution_rate", tier.get("rate", 0.0)))


def min_schedule_rate(core_config: Mapping[str, Any]) -> float:
    """Return the minimum rate that an employee can receive from the core design."""
    status = core_config.get("status", "flat")
    schedule = core_config.get(_SCHEDULES.get(status, ""), [])
    if isinstance(schedule, list) and schedule:
        return min(_tier_rate(tier) for tier in schedule if isinstance(tier, Mapping))
    return float(core_config.get("contribution_rate", 0.0))


def _assert_decimal_rate(base_rate: float) -> None:
    """Fail loudly if a base rate arrived as a percentage rather than a fraction.

    The §401(l) test below compares the disparity rate against the base rate.
    Both must be decimal fractions. A percentage that slipped through (5.0 for
    5%) is 100x too large, so ``min(base_rate, factor)`` would always collapse
    to the factor — silently retiring the base-rate leg of the test and passing
    illegal configurations. A core rate above 100% of pay is never legitimate,
    so treat it as the unit error it is instead of validating against it.
    """
    if base_rate > 1:
        raise ValueError(
            f"Employer core base contribution rate of {base_rate} is not a decimal "
            "fraction. Rates must be expressed as fractions of compensation "
            "(0.05 for 5%), not percentages, or the §401(l) permitted-disparity "
            "check cannot be enforced against them."
        )


def _validation_message(
    *,
    year: int,
    disparity_rate: float,
    limit: float,
    base_rate: float,
    factor: float,
    level: int,
    wage_base: int,
) -> str:
    bound = "base rate" if base_rate <= factor else "disparity factor"
    return (
        f"Employer core integration: disparity_rate {disparity_rate:.2%} exceeds "
        f"the maximum permitted under IRC §401(l) for simulation year {year}. "
        f"The maximum is {limit:.2%} (the lesser of the base contribution rate "
        f"{base_rate:.2%} and the permitted disparity factor {factor:.2%} for an "
        f"integration level of ${level:,} against a taxable wage base of ${wage_base:,}). "
        f"Bound by: {bound}."
    )


def validate_core_integration(
    core_config: Mapping[str, Any], start_year: int, end_year: int
) -> None:
    """Reject a core-integration configuration that violates §401(l) in any year."""
    integration = CoreIntegrationSettings.model_validate(
        core_config.get("integration", {})
    )
    if not integration.enabled:
        return

    base_rate = min_schedule_rate(core_config)
    _assert_decimal_rate(base_rate)
    for year in range(start_year, end_year + 1):
        wage_base = wage_base_for(year)
        level = resolve_level(
            integration.level_mode, integration.level_value, wage_base
        )
        factor = permitted_disparity_factor(level, wage_base)
        permitted_rate = min(base_rate, factor)
        if integration.disparity_rate > permitted_rate:
            raise ValueError(
                _validation_message(
                    year=year,
                    disparity_rate=integration.disparity_rate,
                    limit=permitted_rate,
                    base_rate=base_rate,
                    factor=factor,
                    level=level,
                    wage_base=wage_base,
                )
            )
