"""Exposure-weighted iterative proportional fit of a two-factor rate model.

Every rate the simulator computes has the same shape — a scalar times one
multiplier per demographic axis, optionally times a fixed offset::

    rate = base * row_multiplier[row] * col_multiplier[col] * offset

Each sweep sets a factor to observed events over expected events under the
other factor, which is the closed-form Poisson/IRLS update for a log-linear
model with the offset held fixed. It converges monotonically and needs nothing
beyond the standard library.

Base and multipliers are identified only up to a common scale, so the caller
picks one axis to normalize to an exposure-weighted mean of 1.0; the scale is
folded into the base.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

MAX_ITERATIONS = 200
CONVERGENCE_TOLERANCE = 1e-10

# Bounds so a single freak cell cannot produce an absurd multiplier.
MIN_MULTIPLIER = 0.01
MAX_MULTIPLIER = 25.0

NormalizeAxis = Literal["row", "col", "none"]


@dataclass(frozen=True)
class FactorCell:
    """One cell of the cross-tabulation being fitted."""

    row: str
    col: str
    exposure: float
    events: float
    offset: float = 1.0


@dataclass(frozen=True)
class FactorSolution:
    base: float
    row_multipliers: dict[str, float]
    col_multipliers: dict[str, float]
    converged: bool
    iterations: int


def solve(
    cells: Sequence[FactorCell],
    row_labels: Sequence[str],
    col_labels: Sequence[str],
    *,
    normalize: NormalizeAxis = "row",
) -> FactorSolution:
    """Fit ``base``, ``row_multipliers``, and ``col_multipliers`` to ``cells``."""
    row_multipliers = {label: 1.0 for label in row_labels}
    col_multipliers = {label: 1.0 for label in col_labels}

    total_events = sum(cell.events for cell in cells)
    neutral_expected = sum(cell.exposure * cell.offset for cell in cells)
    if total_events <= 0 or neutral_expected <= 0:
        return FactorSolution(0.0, row_multipliers, col_multipliers, True, 0)

    base = total_events / neutral_expected
    converged = False
    iterations = 0

    for iterations in range(1, MAX_ITERATIONS + 1):
        previous = (base, dict(row_multipliers), dict(col_multipliers))

        _sweep(cells, row_multipliers, col_multipliers, base, axis="row")
        _sweep(cells, col_multipliers, row_multipliers, base, axis="col")

        # Rescale the base so total expected events match total observed. The
        # denominator excludes the base itself — it is what is being solved for.
        unscaled = _expected_without_base(cells, row_multipliers, col_multipliers)
        if unscaled > 0:
            base = total_events / unscaled

        if _converged(previous, base, row_multipliers, col_multipliers):
            converged = True
            break

    if normalize == "row":
        base, row_multipliers = _normalize(cells, base, row_multipliers, axis="row")
    elif normalize == "col":
        base, col_multipliers = _normalize(cells, base, col_multipliers, axis="col")

    return FactorSolution(base, row_multipliers, col_multipliers, converged, iterations)


def _sweep(
    cells: Sequence[FactorCell],
    target: dict[str, float],
    other: dict[str, float],
    base: float,
    *,
    axis: Literal["row", "col"],
) -> None:
    events = {label: 0.0 for label in target}
    expected = {label: 0.0 for label in target}
    for cell in cells:
        label = cell.row if axis == "row" else cell.col
        if label not in target:
            continue
        other_label = cell.col if axis == "row" else cell.row
        events[label] += cell.events
        expected[label] += (
            cell.exposure * cell.offset * base * other.get(other_label, 1.0)
        )

    for label in target:
        if expected[label] <= 0:
            continue
        raw = events[label] / expected[label]
        target[label] = min(MAX_MULTIPLIER, max(MIN_MULTIPLIER, raw))


def _expected_without_base(
    cells: Sequence[FactorCell],
    row_multipliers: dict[str, float],
    col_multipliers: dict[str, float],
) -> float:
    """Total expected events at ``base = 1``."""
    return sum(
        cell.exposure
        * cell.offset
        * row_multipliers.get(cell.row, 1.0)
        * col_multipliers.get(cell.col, 1.0)
        for cell in cells
    )


def _converged(
    previous: tuple[float, dict[str, float], dict[str, float]],
    base: float,
    row_multipliers: dict[str, float],
    col_multipliers: dict[str, float],
) -> bool:
    prior_base, prior_rows, prior_cols = previous
    deltas = [abs(base - prior_base)]
    deltas.extend(abs(row_multipliers[k] - prior_rows[k]) for k in row_multipliers)
    deltas.extend(abs(col_multipliers[k] - prior_cols[k]) for k in col_multipliers)
    return max(deltas) < CONVERGENCE_TOLERANCE


def _normalize(
    cells: Sequence[FactorCell],
    base: float,
    multipliers: dict[str, float],
    *,
    axis: Literal["row", "col"],
) -> tuple[float, dict[str, float]]:
    exposure: dict[str, float] = {}
    for cell in cells:
        label = cell.row if axis == "row" else cell.col
        exposure[label] = exposure.get(label, 0.0) + cell.exposure

    total = sum(exposure.values())
    if total <= 0:
        return base, multipliers

    weighted_mean = (
        sum(multipliers.get(label, 1.0) * value for label, value in exposure.items())
        / total
    )
    if weighted_mean <= 0:
        return base, multipliers
    scaled = {label: value / weighted_mean for label, value in multipliers.items()}
    return base * weighted_mean, scaled


def exposure_by(
    cells: Sequence[FactorCell], axis: Literal["row", "col"]
) -> dict[str, float]:
    """Total exposure per label along one axis."""
    totals: dict[str, float] = {}
    for cell in cells:
        label = cell.row if axis == "row" else cell.col
        totals[label] = totals.get(label, 0.0) + cell.exposure
    return totals
