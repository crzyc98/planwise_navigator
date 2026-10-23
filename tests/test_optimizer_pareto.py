"""Optimizer Pareto-frontier tests."""

from itertools import permutations

import pytest

from planalign_optimizer.models import Candidate, ObjectiveTerm
from planalign_optimizer.pareto import pareto_frontier, select_refinement_anchor

pytestmark = pytest.mark.fast


def test_known_dominated_point_is_excluded() -> None:
    candidates = tuple(
        Candidate(
            candidate_id=name,
            lever_values={},
            status="feasible",
            objective_values={"cost": cost, "participation": participation},
        )
        for name, cost, participation in (
            ("a", 1.0, 0.8),
            ("b", 2.0, 0.9),
            ("c", 3.0, 0.7),
        )
    )
    objectives = (
        ObjectiveTerm(metric="cost", direction="minimize"),
        ObjectiveTerm(metric="participation", direction="maximize"),
    )
    assert pareto_frontier(candidates, objectives) == ("a", "b")


OBJECTIVES = (
    ObjectiveTerm(metric="cost", direction="minimize"),
    ObjectiveTerm(metric="participation", direction="maximize"),
)


def _point(
    identifier: str, cost: float | None, participation: float | None
) -> Candidate:
    return Candidate(
        candidate_id=identifier,
        lever_values={},
        status="feasible",
        objective_values={"cost": cost, "participation": participation},
    )


@pytest.mark.parametrize(
    "cost_scale,participation_scale", [(1, 1), (1000, 1), (1, 100)]
)
@pytest.mark.parametrize("swapped", [False, True])
@pytest.mark.parametrize("direction", ["minimize", "maximize"])
def test_knee_is_independent_of_order_units_and_directions(
    cost_scale: float, participation_scale: float, swapped: bool, direction: str
) -> None:
    sign = 1 if direction == "minimize" else -1
    candidates = tuple(
        _point(name, sign * cost * cost_scale, participation * participation_scale)
        for name, cost, participation in (
            ("a", 100, 0.50),
            ("b", 140, 0.85),
            ("c", 200, 0.90),
        )
    )
    objectives = (ObjectiveTerm(metric="cost", direction=direction), OBJECTIVES[1])
    if swapped:
        objectives = objectives[::-1]
    for ordering in permutations(candidates):
        assert select_refinement_anchor(ordering, objectives) == "b"


@pytest.mark.parametrize(
    "points,expected",
    [
        ([], None),
        ([("b", 100, 0.5)], "b"),
        ([("b", 100, 0.5), ("a", 200, 0.9)], "a"),
        ([("a", 0, 0), ("b", 0.5, 0.5), ("c", 1, 1)], "b"),
        ([("a", 0, 0), ("b", 0.6, 0.4), ("c", 1, 1)], "b"),
        ([("a", 0, 0), ("b", 0.9, 0.1), ("c", 1, 1)], "a"),
        ([("a", 100, 0.5), ("b", 100, 0.9)], "b"),
        ([("b", 100, 0.5), ("a", 100, 0.5)], "a"),
        ([("a", 0, 0), ("z", 0.4, 0.8), ("b", 0.4, 0.8), ("c", 1, 1)], "b"),
        # Equal knee scores prefer the smaller ideal distance, then the ID.
        ([("a", 0, 0), ("z", 0.25, 0.75), ("b", 0.375, 0.875), ("c", 1, 1)], "z"),
        ([("a", 0, 0), ("z", 0.25, 0.5), ("b", 0.5, 0.75), ("c", 1, 1)], "b"),
        # A tiny inward knee must fall back to the closer ideal point.
        ([("a", 0, 0), ("b", 0.2, 0.2000000001), ("c", 0.5, 0.5), ("d", 1, 1)], "c"),
        ([("a", -1e308, 0), ("b", 0, 0.9), ("c", 1e308, 1)], "b"),
    ],
)
def test_anchor_fallbacks_and_ties(
    points: list[tuple[str, float, float]], expected: str | None
) -> None:
    for ordering in permutations(tuple(_point(*point) for point in points)):
        assert select_refinement_anchor(ordering, OBJECTIVES) == expected


@pytest.mark.parametrize("metric", ["cost", "participation"])
@pytest.mark.parametrize("invalid", [None, float("nan"), float("inf"), -float("inf")])
def test_nonfinite_and_missing_values_are_excluded(
    metric: str, invalid: float | None
) -> None:
    valid = _point("b", 100, 0.5)
    values = {"cost": 0.0, "participation": 1.0, metric: invalid}
    invalid_candidate = _point("a", 0, 1).model_copy(
        update={"objective_values": values}
    )
    assert select_refinement_anchor((invalid_candidate, valid), OBJECTIVES) == "b"
    assert select_refinement_anchor((invalid_candidate,), OBJECTIVES) is None
    missing = invalid_candidate.model_copy(update={"objective_values": {}})
    assert select_refinement_anchor((missing,), OBJECTIVES) is None


@pytest.mark.parametrize("status", ["failed", "infeasible", "non_evaluable"])
def test_unsuccessful_candidates_are_excluded(status: str) -> None:
    excluded = _point("a", 0, 1).model_copy(update={"status": status})
    assert (
        select_refinement_anchor((excluded, _point("b", 100, 0.5)), OBJECTIVES) == "b"
    )
    assert select_refinement_anchor((excluded,), OBJECTIVES) is None


def test_exact_duplicates_are_excluded() -> None:
    duplicate = _point("a", 140, 0.85).model_copy(update={"is_duplicate_of": "b"})
    candidates = (
        duplicate,
        _point("b", 140, 0.85),
        _point("c", 100, 0.5),
        _point("d", 200, 0.9),
    )
    for ordering in permutations(candidates):
        assert select_refinement_anchor(ordering, OBJECTIVES) == "b"
    assert select_refinement_anchor((duplicate,), OBJECTIVES) is None
