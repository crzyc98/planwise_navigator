"""Horizon solver: finds raises, hire pay growth and hire pay ratio for a target.

Pure search logic, so it can be tested without a simulation. It measures how
growth responds to each lever, then takes bounded steps from that response. See
``specs/1114-calibration-search/spec.md``.
"""

from __future__ import annotations

from typing import Callable, List, Literal, NamedTuple, Optional, Sequence, Tuple

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import lsq_linear

Vector = NDArray[np.float64]
StopReason = Literal["on_target", "no_further_improvement", "budget_exhausted"]

LEVER_NAMES = ("raises", "hire_pay_growth", "hire_pay_ratio")
_PROBE_STEPS = np.array([0.01, 0.01, 0.05])
_CAGR_WEIGHT = 3.0  # The target comes first; annual rows shape the path.
_MOVE_WEIGHT = 1.0  # Small, so equally good answers prefer the smaller move.
_MIN_STEP = 1e-4
_AT_BOUND = 1e-6


class SolverLimits(NamedTuple):
    """Search bounds and the tolerances that define on target."""

    lower: Vector
    upper: Vector
    cagr_tolerance_pct: float
    guardrail_pct: float
    evaluations: int


class Candidate(NamedTuple):
    levers: Vector
    errors: Vector  # Annual growth minus target, in pp.
    cagr_error: float


class LimitTest(NamedTuple):
    """A controlled rerun with one bound relaxed."""

    lever: str
    bound: Literal["lower", "upper"]
    relaxed_to: float
    cagr_error_before: float
    cagr_error_after: float


class SolverOutcome(NamedTuple):
    best: Candidate
    stop_reason: StopReason
    guardrail_misses: int
    active_bounds: List[str]
    limit_tests: List[LimitTest]


def horizon_cagr_error(
    annual_growth: Sequence[float] | Vector, target_pct: float
) -> float:
    """Compound annual growth minus target, in pp."""
    factors = 1 + np.asarray(annual_growth, dtype=float) / 100
    return float((np.prod(factors) ** (1 / len(factors)) - 1) * 100 - target_pct)


def _misses(candidate: Candidate, limits: SolverLimits) -> int:
    return int(np.sum(np.abs(candidate.errors) > limits.guardrail_pct))


def _on_target(candidate: Candidate, limits: SolverLimits) -> bool:
    return (
        abs(candidate.cagr_error) <= limits.cagr_tolerance_pct
        and _misses(candidate, limits) == 0
    )


def _rank(
    candidate: Candidate, start: Vector, limits: SolverLimits
) -> Tuple[float, int, float, float, float]:
    """Spec tie-break order: CAGR miss, guardrail misses, move, raises, hire growth."""
    cagr_miss = max(abs(candidate.cagr_error) - limits.cagr_tolerance_pct, 0.0)
    return (
        round(cagr_miss, 6),
        _misses(candidate, limits),
        round(float(np.abs(candidate.levers - start).sum()), 6),
        round(float(candidate.levers[0]), 6),
        round(float(candidate.levers[1]), 6),
    )


def _probe(levers: Vector, index: int, limits: SolverLimits) -> Vector:
    """One lever moved inward from any bound it sits on."""
    probe = levers.copy()
    step = _PROBE_STEPS[index]
    room_up = limits.upper[index] - levers[index]
    probe[index] += step if room_up >= step else -step
    return np.clip(probe, limits.lower, limits.upper)


def _step(
    candidate: Candidate, jacobian: Vector, limits: SolverLimits, slope: Vector
) -> Vector:
    """Bounded least-squares move toward zero CAGR and annual error."""
    rows = np.vstack([jacobian, _CAGR_WEIGHT * slope, _MOVE_WEIGHT * np.eye(3)])
    residual = np.concatenate(
        [candidate.errors, [_CAGR_WEIGHT * candidate.cagr_error], np.zeros(3)]
    )
    bounds = (limits.lower - candidate.levers, limits.upper - candidate.levers)
    return lsq_linear(rows, -residual, bounds=bounds).x


def _broyden(
    jacobian: Vector, move: Vector, change: Vector, slope_change: float, slope: Vector
) -> Tuple[Vector, Vector]:
    """Update the measured response with what the last step showed."""
    size = float(move @ move)
    if size == 0:
        return jacobian, slope
    updated = jacobian + np.outer(change - jacobian @ move, move) / size
    return updated, slope + (slope_change - slope @ move) * move / size


def _measure(
    evaluate: Callable[[Vector], Candidate],
    start: Candidate,
    limits: SolverLimits,
) -> Tuple[Vector, Vector, List[Candidate]]:
    """Measure the response to each lever, one probe per lever."""
    columns, slopes, probes = [], [], []
    for index in range(3):
        point = evaluate(_probe(start.levers, index, limits))
        delta = point.levers[index] - start.levers[index]
        columns.append(
            (point.errors - start.errors) / delta if delta else point.errors * 0
        )
        slopes.append((point.cagr_error - start.cagr_error) / delta if delta else 0.0)
        probes.append(point)
    return np.column_stack(columns), np.array(slopes), probes


def _active_bounds(best: Candidate, limits: SolverLimits) -> List[Tuple[int, str]]:
    active: List[Tuple[int, str]] = []
    for index in range(3):
        if best.levers[index] <= limits.lower[index] + _AT_BOUND:
            active.append((index, "lower"))
        elif best.levers[index] >= limits.upper[index] - _AT_BOUND:
            active.append((index, "upper"))
    return active


def _test_limits(
    evaluate: Callable[[Vector], Candidate],
    best: Candidate,
    active: List[Tuple[int, str]],
    limits: SolverLimits,
) -> List[LimitTest]:
    """Rerun with each active bound relaxed, keeping everything else fixed."""
    tests: List[LimitTest] = []
    for index, bound in active:
        sign = 1.0 if bound == "upper" else -1.0
        relaxed = best.levers.copy()
        relaxed[index] += sign * _PROBE_STEPS[index]
        if relaxed[index] < 0:
            continue
        point = evaluate(relaxed)
        tests.append(
            LimitTest(
                LEVER_NAMES[index],
                bound,  # type: ignore[arg-type]
                float(relaxed[index]),
                best.cagr_error,
                point.cagr_error,
            )
        )
    return tests


def solve_horizon(
    evaluate: Callable[[Vector], Candidate],
    start: Vector,
    limits: SolverLimits,
) -> SolverOutcome:
    """Search within the budget, then test any bound the best answer sits on."""
    origin = np.clip(start, limits.lower, limits.upper)
    current = evaluate(origin)
    seen = [current]
    stop = _search(evaluate, current, seen, limits)
    best = min(seen, key=lambda item: _rank(item, origin, limits))
    active = [] if _on_target(best, limits) else _active_bounds(best, limits)
    return SolverOutcome(
        best=best,
        stop_reason=stop,
        guardrail_misses=_misses(best, limits),
        active_bounds=[f"{LEVER_NAMES[i]}:{side}" for i, side in active],
        limit_tests=_test_limits(evaluate, best, active, limits),
    )


def _search(
    evaluate: Callable[[Vector], Candidate],
    current: Candidate,
    seen: List[Candidate],
    limits: SolverLimits,
) -> StopReason:
    if _on_target(current, limits):
        return "on_target"
    jacobian, slope, probes = _measure(evaluate, current, limits)
    seen.extend(probes)
    while len(seen) < limits.evaluations:
        move = _step(current, jacobian, limits, slope)
        if np.abs(move).max() < _MIN_STEP:
            return "no_further_improvement"
        following = evaluate(current.levers + move)
        seen.append(following)
        if _on_target(following, limits):
            return "on_target"
        jacobian, slope = _broyden(
            jacobian,
            move,
            following.errors - current.errors,
            following.cagr_error - current.cagr_error,
            slope,
        )
        current = following
    return "budget_exhausted"


def best_limit_message(tests: Sequence[LimitTest]) -> Optional[str]:
    """Name a limit only when relaxing it was shown to close the gap."""
    helped = [
        test
        for test in tests
        if abs(test.cagr_error_after) < abs(test.cagr_error_before)
    ]
    if not helped:
        return None
    top = min(helped, key=lambda test: abs(test.cagr_error_after))
    return (
        f"Relaxing the {top.bound} limit on {top.lever.replace('_', ' ')} to "
        f"{top.relaxed_to:.1%} moved the miss from {top.cagr_error_before:+.2f}pp to "
        f"{top.cagr_error_after:+.2f}pp."
    )
