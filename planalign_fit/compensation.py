"""Fit the compensation levers observable in a census diff.

Only *merit* is fitted here. A census diff shows one number per employee — the
year-over-year change in gross compensation — and the simulator produces that
number as ``cola_rate + merit_base[level]``. COLA is a policy input the plan
sponsor sets, not a behaviour to be recovered, so it is held at the configured
value and merit absorbs the remainder:

    merit_base[level] = weighted_median(growth | level, continued) - cola[level]

Each employee is weighted by ``1 - promotion_weight`` — how likely their raise
was an ordinary one. A certain promotion contributes nothing and a certain
non-promotion contributes fully, so where the census supplies job levels this
is exactly the old "exclude promotions" rule. Where it does not, promotions are
only *probable*, and down-weighting them beats a hard split that would be wrong
either way (#511). The median (not the mean) is used so a handful of off-cycle
adjustments cannot move a level's merit rate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import numpy as np

from planalign_fit.models import FittedValue
from planalign_fit.priors import Priors
from planalign_fit.smoothing import shrink_ratio
from planalign_fit.transitions import TransitionSet

if TYPE_CHECKING:  # pragma: no cover - typing only
    import duckdb

# Growth outside this band is an off-cycle adjustment (or bad data), not merit.
MIN_PLAUSIBLE_GROWTH = -0.50
MAX_PLAUSIBLE_GROWTH = 1.00


def weighted_median(values: np.ndarray, weights: np.ndarray) -> Optional[float]:
    """Median of ``values`` under ``weights``, interpolated at the midpoint.

    Uses the midpoint convention (each observation spans half its own weight on
    either side of its cumulative position), which reduces *exactly* to an
    interpolated median when every weight is 1 — the property that keeps a fit
    over a census with job levels bit-identical to the pre-#511 behaviour.
    """
    total = float(weights.sum())
    if values.size == 0 or total <= 0:
        return None

    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    sorted_weights = weights[order]
    # Cumulative weight at each observation's midpoint, normalised to [0, 1].
    positions = (np.cumsum(sorted_weights) - 0.5 * sorted_weights) / total
    return float(np.interp(0.5, positions, sorted_values))


def observed_merit_by_level(
    conn: "duckdb.DuckDBPyConnection", table: str
) -> dict[int, tuple[float, float]]:
    """Promotion-weighted median growth and effective exposure per level.

    Exposure is the summed ordinary-raise weight rather than a row count, so
    credibility smoothing downstream sees the evidence actually behind the
    median rather than a headcount that includes probable promotions.
    """
    rows = conn.execute(
        f"""
        SELECT level_id,
               compensation_growth,
               1.0 - promotion_weight AS ordinary_weight
        FROM {table}
        WHERE continued
          AND compensation_growth IS NOT NULL
          AND compensation_growth BETWEEN {MIN_PLAUSIBLE_GROWTH} AND {MAX_PLAUSIBLE_GROWTH}
          AND promotion_weight < 1.0
        ORDER BY level_id
        """
    ).fetchall()

    by_level: dict[int, list[tuple[float, float]]] = {}
    for level_id, growth, weight in rows:
        by_level.setdefault(int(level_id), []).append((float(growth), float(weight)))

    observed: dict[int, tuple[float, float]] = {}
    for level_id, samples in by_level.items():
        values = np.fromiter((s[0] for s in samples), dtype=float, count=len(samples))
        weights = np.fromiter((s[1] for s in samples), dtype=float, count=len(samples))
        median = weighted_median(values, weights)
        if median is not None:
            observed[level_id] = (median, float(weights.sum()))
    return observed


def fit_merit_by_level(
    transitions: TransitionSet,
    priors: Priors,
    *,
    credibility_k: float,
    min_exposure: float,
) -> dict[int, FittedValue]:
    """Fit ``merit_base`` per job level, net of the configured COLA."""
    observed = observed_merit_by_level(transitions.conn, transitions.table)
    config_cola = _config_cola(priors)

    fitted: dict[int, FittedValue] = {}
    for level in transitions.bands.level_ids:
        median_growth, exposure = observed.get(level, (None, 0.0))
        cola = priors.cola_by_level.get(level, config_cola)
        prior_merit = priors.merit_by_level.get(
            level, float(priors.config_value("compensation.merit_budget", 0.035))
        )
        implied = None if median_growth is None else max(0.0, median_growth - cola)
        fitted[level] = FittedValue.from_credibility(
            f"merit_base[level_{level}]",
            shrink_ratio(
                implied,
                exposure,
                prior_merit,
                credibility_k=credibility_k,
                min_exposure=min_exposure,
            ),
        )
    return fitted


def _config_cola(priors: Priors) -> float:
    return float(priors.config_value("compensation.cola_rate", 0.0) or 0.0)


def fit_headcount_growth(
    transitions: TransitionSet, prior: float, *, min_exposure: float
) -> Optional[FittedValue]:
    """Observed annual headcount growth across the snapshot years.

    Growth is measured on the snapshots directly (end-of-year active headcount),
    not on the transition table, so hires and exits both count.
    """
    counts = []
    for snapshot in transitions.snapshot_set:
        row = transitions.conn.execute(
            f"SELECT COUNT(*) FROM banded_{snapshot.year} WHERE is_active"
        ).fetchone()
        if row is None:
            # Skipping a year would silently pair non-adjacent snapshots below.
            return None
        counts.append(float(row[0]))

    ratios = [
        later / earlier - 1.0
        for earlier, later in zip(counts, counts[1:])
        if earlier > 0
    ]
    if not ratios:
        return None

    average = sum(ratios) / len(ratios)
    exposure = sum(counts[:-1])
    return FittedValue.from_credibility(
        "simulation.target_growth_rate",
        shrink_ratio(
            average,
            exposure,
            prior,
            # Headcount growth is a population-level aggregate: a full year of
            # exposure is already conclusive, so it is not shrunk further.
            credibility_k=0.0,
            min_exposure=min_exposure,
        ),
    )
