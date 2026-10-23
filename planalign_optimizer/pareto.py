"""Pareto-efficient candidate selection."""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite, sqrt
from typing import cast

from .models import Candidate, ObjectiveTerm

# Require a meaningful inward knee rather than floating-point noise near a line.
KNEE_TOLERANCE = 1e-9


def select_refinement_anchor(
    candidates: Sequence[Candidate], objectives: Sequence[ObjectiveTerm]
) -> str | None:
    """Select a normalized two-objective knee, falling back to the ideal point.

    Equal normalized weighting is an implicit preference. Knee scores must
    exceed KNEE_TOLERANCE; exact ties use ideal distance, then candidate ID.
    """
    eligible = [
        candidate
        for candidate in candidates
        if candidate.status == "feasible"
        and candidate.is_duplicate_of is None
        and all(
            (value := candidate.objective_values.get(term.metric)) is not None
            and isfinite(value)
            for term in objectives
        )
    ]
    frontier = set(pareto_frontier(eligible, objectives))
    eligible = [item for item in eligible if item.candidate_id in frontier]
    if not eligible:
        return None
    losses = _normalized_losses(eligible, objectives)
    distances = [sum(value**2 for value in point) for point in losses]
    scores = [0.0] * len(eligible)
    if len(objectives) == 2 and len(set(losses)) >= 3:
        if all(len({point[axis] for point in losses}) > 1 for axis in (0, 1)):
            scores = [(1 - x - y) / sqrt(2) for x, y in losses]
    use_knee = max(scores) > KNEE_TOLERANCE
    best = min(
        range(len(eligible)),
        key=lambda index: (
            -scores[index] if use_knee else 0.0,
            distances[index],
            eligible[index].candidate_id,
        ),
    )
    return eligible[best].candidate_id


def _normalized_losses(
    candidates: Sequence[Candidate], objectives: Sequence[ObjectiveTerm]
) -> list[tuple[float, ...]]:
    dimensions: list[list[float]] = []
    for term in objectives:
        values = [
            cast(float, item.objective_values[term.metric]) for item in candidates
        ]
        low, high = min(values), max(values)
        if low == high:
            dimensions.append([0.0] * len(values))
            continue
        # Scaling first keeps subtraction finite even for extreme finite values.
        if not isfinite(high - low):
            scale = max(abs(low), abs(high))
            low, high = low / scale, high / scale
            values = [value / scale for value in values]
        dimensions.append(
            [
                (
                    (value - low) / (high - low)
                    if term.direction == "minimize"
                    else (high - value) / (high - low)
                )
                for value in values
            ]
        )
    return [tuple(values) for values in zip(*dimensions)]


def pareto_frontier(
    candidates: Sequence[Candidate], objectives: Sequence[ObjectiveTerm]
) -> tuple[str, ...]:
    """Return stable candidate IDs that are not dominated on all objectives."""
    feasible = [
        candidate for candidate in candidates if _is_evaluable(candidate, objectives)
    ]
    return tuple(
        candidate.candidate_id
        for candidate in feasible
        if not any(
            _dominates(other, candidate, objectives)
            for other in feasible
            if other.candidate_id != candidate.candidate_id
        )
    )


def _is_evaluable(candidate: Candidate, objectives: Sequence[ObjectiveTerm]) -> bool:
    return candidate.status == "feasible" and all(
        candidate.objective_values.get(term.metric) is not None for term in objectives
    )


def _dominates(
    first: Candidate, second: Candidate, objectives: Sequence[ObjectiveTerm]
) -> bool:
    comparisons = []
    strict = []
    for term in objectives:
        left = first.objective_values[term.metric]
        right = second.objective_values[term.metric]
        if left is None or right is None:
            return False
        if term.direction == "minimize":
            comparisons.append(left <= right)
            strict.append(left < right)
        else:
            comparisons.append(left >= right)
            strict.append(left > right)
    return all(comparisons) and any(strict)
