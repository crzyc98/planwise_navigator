"""Optimizer Pareto-frontier tests."""

import pytest

from planalign_optimizer.models import Candidate, ObjectiveTerm
from planalign_optimizer.pareto import pareto_frontier

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
