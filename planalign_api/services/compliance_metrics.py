"""Shared dollar-limit calculations for NDT and compliance reporting."""

from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

LimitStatus = Literal[
    "below_threshold", "near_limit", "at_limit", "over_limit", "unavailable"
]


def cents(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def limit_status(
    amount: float | None, limit: float | None, threshold: float
) -> LimitStatus:
    if amount is None or limit is None or limit <= 0 or amount < 0:
        return "unavailable"
    amount_cents, limit_cents = cents(amount), cents(limit)
    if amount_cents > limit_cents:
        return "over_limit"
    if amount_cents == limit_cents:
        return "at_limit"
    if amount_cents >= limit_cents * Decimal(str(threshold)):
        return "near_limit"
    return "below_threshold"


def base_deferrals(
    contributions: float,
    base_limit: float,
    age: int | None,
    catch_up_age: int,
    total_deferral_limit: float | None,
) -> float:
    """Exclude modeled catch-up only for employees known to be age eligible."""
    if age is not None and age >= catch_up_age and total_deferral_limit is not None:
        capacity = max(0, total_deferral_limit - base_limit)
        return contributions - min(max(0, contributions - base_limit), capacity)
    return contributions


def annual_additions(
    contributions: float,
    match: float,
    core: float,
    base_limit: float,
    age: int | None,
    catch_up_age: int,
    total_deferral_limit: float | None,
) -> float:
    return float(
        cents(
            base_deferrals(
                contributions, base_limit, age, catch_up_age, total_deferral_limit
            )
        )
        + cents(match)
        + cents(core)
    )


def applicable_deferral_limit(
    age: int | None,
    base: float,
    ordinary: float,
    enhanced: float,
    catch_up_age: int,
    enhanced_min: int,
    enhanced_max: int,
) -> float | None:
    if age is None or age < 0:
        return None
    if enhanced_min <= age <= enhanced_max:
        return enhanced
    return ordinary if age >= catch_up_age else base
