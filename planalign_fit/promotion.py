"""Decide how a fit learns its promotion rate, and how much to trust it (#511).

A promotion is a move to a higher job level. Where the census carries the level
that is directly observable, and this module gets out of the way. Where it does
not, level is derived from compensation banding — and then *any* raise that
crosses a band boundary reads as a promotion, which an ordinary merit raise
does on its own. Measured on a synthetic population with a true 6% rate, that
mistake fits 9.1% over three snapshots and 15.2% over five. The error grows
with the length of the history because nobody leaves a compensation band except
by crossing it, so an incumbent cohort drifts up and piles against its ceiling
— which means the estimate degrades exactly as a client supplies more data.

So when the level column cannot be trusted, the rate is recovered from the
*shape* of the raise distribution instead. The simulator builds a raise one of
two ways — ordinary (COLA plus merit) or promotion (a much larger step) — which
makes the observed distribution a two-component mixture, and fitting one back
recovers both the promotion rate and the ordinary-raise centre in a single
pass. That simultaneity matters: it is what stops promotion from being defined
in terms of a merit estimate that was itself measured off the promotion
classification.

Some populations will not separate — a client whose promotion step is small, or
whose ordinary raises are widely spread. Reporting a confident number there
would trade one wrong answer for another, so those levels keep their configured
default and say so, and a fit resting on too little of the population publishes
no promotion hazard at all.

A note on what "a level keeps its default" can mean here. The hazard is
``base x age_multiplier x tenure_multiplier x level_factor(level)`` and the
level factor is a *fixed structural constant*, not a fitted per-level rate —
there is no per-level number in the seed files to leave alone. So a level that
does not separate is **withheld from the fit entirely**, contributing neither
exposure nor events. Its rate then follows from the fitted base and the
unchanged level factor, which is the model's own structure rather than an
observation this module invented. The report names those levels and shows the
rate they fell back to.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from planalign_fit.compensation import MAX_PLAUSIBLE_GROWTH, MIN_PLAUSIBLE_GROWTH
from planalign_fit.mixture import fit_two_component
from planalign_fit.models import (
    LevelSeparation,
    PromotionBasis,
    PromotionClassification,
)
from planalign_fit.priors import Priors
from planalign_fit.transitions import TransitionSet

WEIGHTS_TABLE = "fit_promotion_weights"

# --- Analyst-adjustable thresholds (defaults) --------------------------------
# Both are data-quality judgements about a particular census, so `planalign fit`
# exposes them. Non-default values are recorded in the report and the pack
# manifest.

# Job level must be present on both ends of at least this share of linked
# transitions before the column is treated as authoritative. A partially
# populated column is worse than none: it silently mixes measured and
# band-derived promotions in one fit.
DEFAULT_LEVEL_COVERAGE_THRESHOLD = 0.95

# The levels that separated must cover at least this share of experienced
# exposure, otherwise the hazard is reported not fitted rather than published
# on the strength of a corner of the population.
DEFAULT_SEPARATION_EXPOSURE_GATE = 0.50

# --- Fixed method constants (deliberately NOT configurable) ------------------
# Tuning these until a number appears is indistinguishable from manufacturing a
# promotion rate, so there is no CLI, config, or environment path to them.

# Component means must be at least this many pooled standard deviations apart.
# Below it the posteriors sit near a coin flip: a two-component model may fit
# better without the components being tellable apart.
SEPARATION_MIN_DISTANCE = 2.0

# A two-component model must also beat a single Gaussian on BIC. The distance
# test alone would pass whenever one component chases a few outliers; BIC's
# parameter penalty is what refuses that.
SEPARATION_MIN_BIC_GAIN = 0.0


def classify(
    transitions: TransitionSet,
    priors: Priors,
    *,
    level_coverage_threshold: float = DEFAULT_LEVEL_COVERAGE_THRESHOLD,
    separation_exposure_gate: float = DEFAULT_SEPARATION_EXPOSURE_GATE,
    min_exposure: float = 0.0,
) -> PromotionClassification:
    """Decide how this fit learns its promotion rate, and write the weights.

    Mutates ``promotion_weight`` on the transition table when the estimated
    path is taken. On the measured path the seeded weights already hold the
    observed flag, so nothing is written.
    """
    coverage = transitions.observability.level_coverage

    if coverage >= level_coverage_threshold:
        _restrict_measured_exposure(transitions)
        return PromotionClassification(
            basis=PromotionBasis.MEASURED,
            level_coverage=coverage,
            level_coverage_threshold=level_coverage_threshold,
            exposure_gate=separation_exposure_gate,
            reason=(
                f"the census supplies a job level for {coverage:.0%} of linked "
                "employees, so promotions were measured directly from level moves"
            ),
        )

    levels = _fit_levels(transitions, priors, min_exposure=min_exposure)
    total_exposure = sum(level.exposure for level in levels)
    separated_exposure = sum(level.exposure for level in levels if level.separated)
    share = separated_exposure / total_exposure if total_exposure > 0 else 0.0

    if share < separation_exposure_gate:
        _zero_weights(transitions)
        return PromotionClassification(
            basis=PromotionBasis.NOT_FITTED,
            level_coverage=coverage,
            level_coverage_threshold=level_coverage_threshold,
            exposure_gate=separation_exposure_gate,
            separated_exposure_share=share,
            levels=levels,
            reason=(
                "promotions could not be told apart from ordinary raises in "
                f"enough of this population — the levels that separated hold "
                f"{share:.0%} of exposure, below the {separation_exposure_gate:.0%} "
                "needed to publish a rate"
            ),
        )

    _write_weights(transitions, levels)
    return PromotionClassification(
        basis=PromotionBasis.ESTIMATED,
        level_coverage=coverage,
        level_coverage_threshold=level_coverage_threshold,
        exposure_gate=separation_exposure_gate,
        separated_exposure_share=share,
        levels=levels,
        reason=(
            f"no usable job level (coverage {coverage:.0%}, threshold "
            f"{level_coverage_threshold:.0%}), so promotions were separated from "
            f"ordinary raises by their size across {share:.0%} of exposure"
        ),
    )


def separated_levels(classification: Optional[PromotionClassification]) -> list[int]:
    """Levels whose evidence may enter the hazard fit.

    An empty list means "no restriction" — the measured path uses every level.
    """
    if classification is None or classification.basis is not PromotionBasis.ESTIMATED:
        return []
    return [level.level_id for level in classification.levels if level.separated]


def exposure_filter(classification: Optional[PromotionClassification]) -> str:
    """SQL predicate restricting promotion exposure to trustworthy rows."""
    if classification is None:
        return "TRUE"
    if classification.basis is PromotionBasis.MEASURED:
        # A transition without a level at both ends cannot show a level move,
        # so counting it as a non-promotion would deflate the rate.
        return "has_source_level"
    levels = separated_levels(classification)
    if not levels:
        return "TRUE"
    return "level_id IN (" + ", ".join(str(level) for level in levels) + ")"


def _restrict_measured_exposure(transitions: TransitionSet) -> None:
    """Zero the weight of rows the measured path cannot speak to."""
    transitions.conn.execute(
        f"""
        UPDATE {transitions.table}
        SET promotion_weight = 0.0
        WHERE NOT has_source_level
        """
    )


def _zero_weights(transitions: TransitionSet) -> None:
    transitions.conn.execute(f"UPDATE {transitions.table} SET promotion_weight = 0.0")


def _fit_levels(
    transitions: TransitionSet, priors: Priors, *, min_exposure: float
) -> list[LevelSeparation]:
    """Fit one raise mixture per job level and judge whether it separated."""
    top_level = max(transitions.bands.level_ids)
    results: list[LevelSeparation] = []

    for level_id in transitions.bands.level_ids:
        rows = transitions.conn.execute(
            f"""
            SELECT employee_id, from_year, compensation_growth
            FROM {transitions.table}
            WHERE continued AND level_id = ?
            ORDER BY employee_id, from_year
            """,
            [level_id],
        ).fetchall()
        exposure = float(len(rows))

        if level_id == top_level:
            results.append(
                LevelSeparation(
                    level_id=level_id,
                    separated=False,
                    exposure=exposure,
                    reason="the highest job level — nobody can be promoted out of it",
                )
            )
            continue

        eligible = [
            row
            for row in rows
            if row[2] is not None
            and MIN_PLAUSIBLE_GROWTH <= row[2] <= MAX_PLAUSIBLE_GROWTH
            and row[2] > 0.0
        ]
        if exposure < min_exposure or len(eligible) < 2:
            results.append(
                LevelSeparation(
                    level_id=level_id,
                    separated=False,
                    exposure=exposure,
                    reason=(
                        f"too little exposure ({exposure:,.0f}) to establish "
                        "whether raises separate into two kinds"
                    ),
                )
            )
            continue

        values = np.fromiter(
            (row[2] for row in eligible), dtype=float, count=len(eligible)
        )
        fit = fit_two_component(
            values,
            ordinary_guess=priors.cola_prior(level_id) + priors.merit_prior(level_id),
            promotion_guess=priors.cola_prior(level_id) + priors.promotion_raise,
        )
        if fit is None:
            results.append(
                LevelSeparation(
                    level_id=level_id,
                    separated=False,
                    exposure=exposure,
                    reason="too few raises to fit a distribution",
                )
            )
            continue

        separated, reason = _verdict(fit)
        # The promotion component's weight covers only the employees that were
        # fitted; rescale to the level's full exposure so a level of pay freezes
        # is not read as a level of promotions.
        rate = fit.promotion.weight * (len(eligible) / exposure) if exposure else 0.0
        results.append(
            LevelSeparation(
                level_id=level_id,
                separated=separated,
                exposure=exposure,
                reason=reason,
                estimated_rate=rate if separated else None,
                ordinary_location=fit.ordinary.mean if separated else None,
                promotion_location=fit.promotion.mean if separated else None,
                standardized_distance=fit.standardized_distance,
                bic_improvement=fit.bic_improvement,
                converged=fit.converged,
            )
        )
        if separated:
            _stash_weights(transitions, level_id, eligible, fit.responsibilities)

    return results


def _verdict(fit) -> tuple[bool, str]:
    """Both conditions must hold; each catches what the other misses.

    Order matters for the *reason*, not the outcome. Overlapping components
    make EM wander, so a genuinely inseparable level tends to exhaust the
    iteration cap as well as fail the distance floor — and "did not converge"
    would send an analyst looking for a numerical knob when the real answer is
    that their data cannot tell the two kinds of raise apart. So the
    substantive checks are reported first, and non-convergence is only the
    stated reason when a fit would otherwise have passed.
    """
    if not math.isfinite(fit.bic_improvement):
        return False, "the raise distribution did not resolve into two components"
    if fit.bic_improvement <= SEPARATION_MIN_BIC_GAIN:
        return False, (
            "a single kind of raise explains this level better than two, so "
            "there is no promotion component to measure"
        )
    if fit.standardized_distance < SEPARATION_MIN_DISTANCE:
        return False, (
            f"promotion and ordinary raises overlap too much "
            f"({fit.standardized_distance:.1f} pooled standard deviations apart, "
            f"{SEPARATION_MIN_DISTANCE:.0f} needed) to tell them apart"
        )
    if not fit.converged:
        return False, (
            "the raise distribution did not settle on a stable split within "
            "the iteration limit"
        )
    return True, (
        f"separated by {fit.standardized_distance:.1f} pooled standard deviations"
    )


def _stash_weights(
    transitions: TransitionSet,
    level_id: int,
    rows: list,
    responsibilities: "np.ndarray",
) -> None:
    """Hold one level's fitted weights until every level has been fitted."""
    conn = transitions.conn
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {WEIGHTS_TABLE} (
            employee_id VARCHAR,
            from_year INTEGER,
            weight DOUBLE
        )
        """
    )
    conn.executemany(
        f"INSERT INTO {WEIGHTS_TABLE} VALUES (?, ?, ?)",
        [
            (row[0], row[1], float(weight))
            for row, weight in zip(rows, responsibilities)
        ],
    )


def _write_weights(transitions: TransitionSet, levels: list[LevelSeparation]) -> None:
    """Apply the fitted weights, forcing zero everywhere they cannot apply."""
    conn = transitions.conn
    conn.execute(f"UPDATE {transitions.table} SET promotion_weight = 0.0")

    weights_exist = conn.execute(
        "SELECT COUNT(*) FROM duckdb_tables() WHERE table_name = ?",
        [WEIGHTS_TABLE],
    ).fetchone()[0]
    if not weights_exist:
        return

    conn.execute(
        f"""
        UPDATE {transitions.table} AS t
        SET promotion_weight = w.weight
        FROM {WEIGHTS_TABLE} AS w
        WHERE t.employee_id = w.employee_id
          AND t.from_year = w.from_year
        """
    )
    conn.execute(f"DROP TABLE {WEIGHTS_TABLE}")
