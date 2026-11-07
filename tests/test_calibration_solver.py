"""Horizon solver logic, on a synthetic response with no simulation."""

import numpy as np
import pytest

from planalign_orchestrator.calibration_solver import (
    Candidate,
    SolverLimits,
    best_limit_message,
    horizon_cagr_error,
    solve_horizon,
)

pytestmark = pytest.mark.fast

YEARS = np.arange(10)
FADE = 0.8**YEARS  # Raises fade.
BUILD = 1 - 0.8**YEARS  # Hire pay growth builds.
TARGET = 5.5


def response(levers: np.ndarray) -> Candidate:
    """Annual growth shaped like the study: raises fade, hire growth builds."""
    raises, hire, ratio = levers
    growth = (
        1.0
        + 80 * raises * FADE
        + 100 * hire * BUILD
        + 30 * (ratio - 1) * FADE
        + 20 * raises
    )
    return Candidate(levers.copy(), growth - TARGET, horizon_cagr_error(growth, TARGET))


def limits(**changes: float) -> SolverLimits:
    values = {
        "lower": np.array([0.01, 0.0, 0.9]),
        "upper": np.array([0.10, 0.08, 1.1]),
        "cagr_tolerance_pct": 0.25,
        "guardrail_pct": 0.5,
        "evaluations": 12,
    }
    return SolverLimits(**{**values, **changes})


def counted(calls: list) -> object:
    def evaluate(levers: np.ndarray) -> Candidate:
        calls.append(levers.copy())
        return response(levers)

    return evaluate


def test_cagr_error_compounds() -> None:
    assert horizon_cagr_error([10.0, 10.0], 10.0) == pytest.approx(0.0)
    assert horizon_cagr_error([0.0, 21.0], 10.0) == pytest.approx(0.0)


def test_solves_within_budget_and_bounds() -> None:
    calls: list = []
    outcome = solve_horizon(counted(calls), np.array([0.03, 0.0, 1.0]), limits())
    assert abs(outcome.best.cagr_error) <= 0.25
    assert len(calls) <= 12
    assert all(
        (c >= limits().lower).all() and (c <= limits().upper).all() for c in calls
    )


def test_is_deterministic() -> None:
    first = solve_horizon(response, np.array([0.03, 0.0, 1.0]), limits())
    second = solve_horizon(response, np.array([0.03, 0.0, 1.0]), limits())
    assert np.array_equal(first.best.levers, second.best.levers)


def test_stops_at_once_when_already_on_target() -> None:
    def flat(levers: np.ndarray) -> Candidate:
        return Candidate(levers.copy(), np.zeros(10), 0.0)

    calls: list = []

    def evaluate(levers: np.ndarray) -> Candidate:
        calls.append(1)
        return flat(levers)

    outcome = solve_horizon(evaluate, np.array([0.05, 0.03, 1.0]), limits())
    assert outcome.stop_reason == "on_target"
    assert len(calls) == 1
    assert outcome.limit_tests == []


def test_a_tight_bound_is_tested_before_it_is_blamed() -> None:
    tight = limits(upper=np.array([0.02, 0.01, 1.0]), lower=np.array([0.01, 0.0, 0.9]))
    outcome = solve_horizon(response, np.array([0.02, 0.01, 1.0]), tight)
    assert outcome.stop_reason != "on_target"
    assert "raises:upper" in outcome.active_bounds
    test = next(t for t in outcome.limit_tests if t.lever == "raises")
    assert abs(test.cagr_error_after) < abs(test.cagr_error_before)
    assert "upper limit on" in (best_limit_message(outcome.limit_tests) or "")


def test_no_limit_named_when_relaxing_does_not_help() -> None:
    def stuck(levers: np.ndarray) -> Candidate:
        return Candidate(levers.copy(), np.full(10, -2.0), -2.0)

    outcome = solve_horizon(stuck, np.array([0.1, 0.08, 1.1]), limits())
    assert outcome.stop_reason != "on_target"
    assert best_limit_message(outcome.limit_tests) is None
