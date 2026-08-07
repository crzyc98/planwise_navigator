"""Supported levers and deterministic bounded design-space sampling."""

from __future__ import annotations

import itertools
import math
import random
from typing import Final

from .models import DesignSpaceSpec, LeverSpec, LeverValue

LEVER_REGISTRY: Final[dict[str, tuple[str | int, ...]]] = {
    "employer_match.tier_1_rate": (
        "employer_match",
        "formulas",
        "*",
        "tiers",
        0,
        "match_rate",
    ),
    "employer_match.tier_2_rate": (
        "employer_match",
        "formulas",
        "*",
        "tiers",
        1,
        "match_rate",
    ),
    "employer_match.tier_3_rate": (
        "employer_match",
        "formulas",
        "*",
        "tiers",
        2,
        "match_rate",
    ),
    "employer_match.tier_1_cap": (
        "employer_match",
        "formulas",
        "*",
        "tiers",
        0,
        "employee_max",
    ),
    "employer_match.tier_2_cap": (
        "employer_match",
        "formulas",
        "*",
        "tiers",
        1,
        "employee_max",
    ),
    "employer_match.tier_3_cap": (
        "employer_match",
        "formulas",
        "*",
        "tiers",
        2,
        "employee_max",
    ),
    "employer_match.max_match_percentage": (
        "employer_match",
        "formulas",
        "*",
        "max_match_percentage",
    ),
    "employer_match.eligibility.minimum_tenure_years": (
        "employer_match",
        "eligibility",
        "minimum_tenure_years",
    ),
    "employer_match.eligibility.minimum_hours_annual": (
        "employer_match",
        "eligibility",
        "minimum_hours_annual",
    ),
    "auto_enrollment.enabled": ("enrollment", "auto_enrollment", "enabled"),
    "auto_enrollment.default_deferral_rate": (
        "enrollment",
        "auto_enrollment",
        "default_deferral_rate",
    ),
    "auto_enrollment.scope": ("enrollment", "auto_enrollment", "scope"),
    "auto_escalation.enabled": ("deferral_auto_escalation", "enabled"),
    "auto_escalation.annual_increase_rate": (
        "deferral_auto_escalation",
        "increment_amount",
    ),
    "auto_escalation.maximum_rate": ("deferral_auto_escalation", "maximum_rate"),
    "eligibility.waiting_period_days": ("eligibility", "waiting_period_days"),
    "eligibility.minimum_age": ("plan_eligibility", "minimum_age"),
    "vesting_schedule": ("employer_match", "formulas", "*", "vesting_schedule"),
}

CandidateKey = tuple[tuple[str, str, object], ...]


def candidate_identity(values: dict[str, LeverValue]) -> CandidateKey:
    """Return an exact, order-independent identity without numeric rounding."""
    return tuple(
        (name, type(value).__name__, value.hex() if isinstance(value, float) else value)
        for name, value in sorted(values.items())
    )


def sample_candidates(
    design_space: DesignSpaceSpec, candidate_count: int, *, seed: int
) -> list[dict[str, LeverValue]]:
    """Generate deterministic grid seeds followed by coordinate refinements."""
    if candidate_count < 1:
        raise ValueError("candidate_count must be >= 1")
    if not design_space.levers:
        return [{}]
    if all(lever.kind == "discrete" for lever in design_space.levers):
        return _discrete_grid(design_space.levers, candidate_count, seed=seed)

    rng = random.Random(seed)
    seed_count = max(1, math.ceil(candidate_count * 0.6))
    candidates = _stratified_seeds(design_space.levers, seed_count, rng)
    _refine_coordinates(candidates, design_space.levers, candidate_count, rng)
    return _unique(candidates)[:candidate_count]


def refine_candidates(
    design_space: DesignSpaceSpec,
    anchor: dict[str, LeverValue],
    candidate_count: int,
    *,
    seed: int,
    exclude: set[CandidateKey] | None = None,
) -> list[dict[str, LeverValue]]:
    """Generate coordinate moves around the best evaluated design so far."""
    if candidate_count < 1 or not design_space.levers:
        return []
    rng = random.Random(seed)
    seen = set(exclude or set())
    refinements: list[dict[str, LeverValue]] = []
    attempt = 0
    limit = max(100, candidate_count * len(design_space.levers) * 20)
    while len(refinements) < candidate_count and attempt < limit:
        lever = design_space.levers[attempt % len(design_space.levers)]
        candidate = dict(anchor)
        candidate[lever.name] = _refined_value(
            anchor[lever.name], lever, attempt, rng, len(design_space.levers)
        )
        identity = candidate_identity(candidate)
        if identity not in seen:
            seen.add(identity)
            refinements.append(candidate)
        attempt += 1
    return refinements


def _discrete_grid(
    levers: tuple[LeverSpec, ...], candidate_count: int, *, seed: int
) -> list[dict[str, LeverValue]]:
    """Cover the full discrete grid, or a representative sample of it.

    ``itertools.product`` varies the last lever fastest, so naively slicing
    its first ``candidate_count`` entries leaves every earlier lever pinned
    near its first choice whenever the budget is smaller than the full grid.
    A deterministic, seeded, budget-sized sample spread across the whole grid
    keeps every lever actually explored instead of exploring a narrow slice.
    """
    domains = [lever.choices or () for lever in levers]
    full = list(itertools.product(*domains))
    points = (
        full
        if len(full) <= candidate_count
        else _evenly_spread_sample(full, candidate_count, seed)
    )
    return [
        {lever.name: value for lever, value in zip(levers, point, strict=True)}
        for point in points
    ]


def _evenly_spread_sample(
    population: list[tuple[LeverValue, ...]], count: int, seed: int
) -> list[tuple[LeverValue, ...]]:
    rng = random.Random(seed)
    indices = sorted(rng.sample(range(len(population)), count))
    return [population[index] for index in indices]


def _stratified_seeds(
    levers: tuple[LeverSpec, ...], count: int, rng: random.Random
) -> list[dict[str, LeverValue]]:
    columns: dict[str, list[LeverValue]] = {}
    for lever in levers:
        if lever.kind == "discrete":
            choices = list(lever.choices or ())
            values = [choices[index % len(choices)] for index in range(count)]
            rng.shuffle(values)
        else:
            lower, upper = lever.bounds or (0.0, 0.0)
            values = [
                lower + ((index + rng.random()) / count) * (upper - lower)
                for index in range(count)
            ]
            rng.shuffle(values)
        columns[lever.name] = values
    return [
        {lever.name: columns[lever.name][index] for lever in levers}
        for index in range(count)
    ]


def _refine_coordinates(
    candidates: list[dict[str, LeverValue]],
    levers: tuple[LeverSpec, ...],
    target: int,
    rng: random.Random,
) -> None:
    """Add progressively smaller one-coordinate moves around seeded points."""
    seen = {candidate_identity(values) for values in candidates}
    attempt = 0
    max_attempts = max(100, target * len(levers) * 20)
    while len(candidates) < target and attempt < max_attempts:
        base = dict(candidates[attempt % len(candidates)])
        lever = levers[attempt % len(levers)]
        candidate = dict(base)
        candidate[lever.name] = _refined_value(
            base[lever.name], lever, attempt, rng, len(levers)
        )
        identity = candidate_identity(candidate)
        if identity not in seen:
            seen.add(identity)
            candidates.append(candidate)
        attempt += 1


def _refined_value(
    current: LeverValue,
    lever: LeverSpec,
    attempt: int,
    rng: random.Random,
    lever_count: int,
) -> LeverValue:
    """Move one lever a fraction of its range, shrinking every full cycle.

    ``lever_count`` is the searched design space's own lever count (not the
    global lever registry) — one full cycle through every lever is what
    should trigger the next step-size halving, so refinement actually
    narrows within a realistic run budget instead of staying coarse for the
    first ~20 attempts regardless of how small the design space is.
    """
    if lever.kind == "discrete":
        choices = lever.choices or ()
        return choices[(choices.index(current) + 1 + attempt) % len(choices)]
    lower, upper = lever.bounds or (0.0, 0.0)
    span = upper - lower
    direction = -1.0 if attempt % 2 else 1.0
    step = span / (4.0 * (1 + attempt // max(1, lever_count)))
    jitter = 0.5 + rng.random() * 0.5
    return min(upper, max(lower, float(current) + direction * step * jitter))


def _unique(
    candidates: list[dict[str, LeverValue]],
) -> list[dict[str, LeverValue]]:
    seen: set[CandidateKey] = set()
    unique: list[dict[str, LeverValue]] = []
    for values in candidates:
        identity = candidate_identity(values)
        if identity not in seen:
            seen.add(identity)
            unique.append(values)
    return unique
