"""Optimizer design-space tests."""

import pytest

from planalign_optimizer.design_space import candidate_identity, sample_candidates
from planalign_optimizer.models import DesignSpaceSpec, LeverSpec

pytestmark = pytest.mark.fast


def test_sampler_stays_inside_mixed_domains() -> None:
    space = DesignSpaceSpec(
        levers=(
            LeverSpec(
                name="auto_enrollment.default_deferral_rate",
                kind="continuous",
                bounds=(0.03, 0.08),
            ),
            LeverSpec(
                name="auto_enrollment.scope",
                kind="discrete",
                choices=("new_hires_only", "all_eligible_employees"),
            ),
        )
    )
    values = sample_candidates(space, 12, seed=42)
    assert 1 <= len(values) <= 12
    assert all(0.03 <= item[space.levers[0].name] <= 0.08 for item in values)
    assert all(item[space.levers[1].name] in space.levers[1].choices for item in values)


def test_zero_and_one_lever_spaces_are_valid() -> None:
    assert sample_candidates(DesignSpaceSpec(), 5, seed=1) == [{}]
    one = DesignSpaceSpec(
        levers=(
            LeverSpec(
                name="auto_enrollment.scope", kind="discrete", choices=("a", "b")
            ),
        )
    )
    assert sample_candidates(one, 5, seed=1) == [
        {"auto_enrollment.scope": "a"},
        {"auto_enrollment.scope": "b"},
    ]


def test_candidate_identity_is_exact_not_tolerant() -> None:
    first = {"x": 0.1}
    assert candidate_identity(first) == candidate_identity(dict(first))
    assert candidate_identity(first) != candidate_identity({"x": 0.10000000000000002})


def test_truncated_discrete_grid_still_varies_every_lever() -> None:
    """A budget smaller than the full grid must not pin early levers to one choice.

    ``itertools.product`` varies its last domain fastest, so lexicographically
    truncating it (the pre-fix behavior) would leave the first lever fixed at
    its first choice across every sampled candidate. The seeded, spread
    sample must not have that property.
    """
    space = DesignSpaceSpec(
        levers=(
            LeverSpec(name="a", kind="discrete", choices=("a1", "a2", "a3", "a4")),
            LeverSpec(name="b", kind="discrete", choices=("b1", "b2", "b3", "b4")),
        )
    )
    values = sample_candidates(space, 6, seed=7)
    assert len(values) == 6
    assert len({item["a"] for item in values}) > 1
    assert len({item["b"] for item in values}) > 1


def test_discrete_grid_is_deterministic_under_the_same_seed() -> None:
    space = DesignSpaceSpec(
        levers=(LeverSpec(name="a", kind="discrete", choices=("a1", "a2", "a3", "a4")),)
    )
    assert sample_candidates(space, 2, seed=3) == sample_candidates(space, 2, seed=3)


def test_full_grid_is_exhausted_when_budget_covers_it() -> None:
    space = DesignSpaceSpec(
        levers=(LeverSpec(name="a", kind="discrete", choices=("a1", "a2", "a3")),)
    )
    values = sample_candidates(space, 50, seed=1)
    assert {item["a"] for item in values} == {"a1", "a2", "a3"}
    assert len(values) == 3
