"""Pareto-efficient candidate selection."""

from __future__ import annotations

from collections.abc import Sequence

from .models import Candidate, ObjectiveTerm


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
