"""Fit the multiplicative hazards the simulator already evaluates.

Both hazards share one functional form::

    rate = base * age_multiplier[age_band] * tenure_multiplier[tenure_band]
                * level_factor(level_id)

so both go through the same exposure-weighted iterative proportional fit
(:mod:`planalign_fit.ipf`) with the level factor as a fixed offset. That factor
stays at the shipped structural constants — ``level_discount_factor`` for
termination, ``level_dampener_factor`` for promotion — because a short census
history cannot separate a level effect from the compensation banding that
assigns the level in the first place. The fit report lists those constants
under "not fitted".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional, Sequence

from planalign_fit import ipf
from planalign_fit.bands import BandDefinitions
from planalign_fit.models import CellObservation, FittedValue, HazardFit
from planalign_fit.priors import HazardPriors, prior_for_bands
from planalign_fit.smoothing import shrink_ratio, shrink_toward
from planalign_fit.transitions import TransitionError, TransitionSet

if TYPE_CHECKING:  # pragma: no cover - typing only
    import duckdb

LevelFactor = Callable[[int, dict[str, float]], float]


def termination_level_factor(level_id: int, constants: dict[str, float]) -> float:
    """``GREATEST(min_level_discount_multiplier, 1 - discount * (level - 1))``."""
    discount = constants.get("level_discount_factor", 0.0)
    floor = constants.get("min_level_discount_multiplier", 0.0)
    return max(floor, 1.0 - discount * (level_id - 1))


def promotion_level_factor(level_id: int, constants: dict[str, float]) -> float:
    """``GREATEST(0, 1 - level_dampener_factor * (level - 1))``."""
    dampener = constants.get("level_dampener_factor", 0.0)
    return max(0.0, 1.0 - dampener * (level_id - 1))


def _to_factor_cells(
    cells: Sequence[CellObservation], offset: Callable[[int], float]
) -> list[ipf.FactorCell]:
    return [
        ipf.FactorCell(
            row=cell.age_band,
            col=cell.tenure_band,
            exposure=cell.exposure,
            events=cell.events,
            offset=offset(cell.level_id),
        )
        for cell in cells
    ]


def fit_hazard(
    kind: str,
    cells: Sequence[CellObservation],
    priors: HazardPriors,
    bands: BandDefinitions,
    *,
    level_factor: LevelFactor,
    credibility_k: float,
    min_exposure: float,
) -> HazardFit:
    """Fit one hazard and credibility-smooth every fitted number."""
    age_labels = bands.age_band_labels
    tenure_labels = bands.tenure_band_labels
    age_priors = prior_for_bands(priors.age_multipliers, age_labels)
    tenure_priors = prior_for_bands(priors.tenure_multipliers, tenure_labels)

    factor_cells = _to_factor_cells(
        cells, lambda level_id: level_factor(level_id, priors.level_constants)
    )
    solution = ipf.solve(factor_cells, age_labels, tenure_labels, normalize="row")

    total_events = sum(cell.events for cell in cells)
    total_exposure = sum(cell.exposure for cell in cells)
    age_exposure = ipf.exposure_by(factor_cells, "row")
    tenure_exposure = ipf.exposure_by(factor_cells, "col")

    base = FittedValue.from_credibility(
        f"{kind}_base_rate",
        shrink_ratio(
            solution.base if total_events > 0 else None,
            total_exposure,
            priors.base_rate,
            credibility_k=credibility_k,
            min_exposure=min_exposure,
        ),
    )
    age_multipliers = _smooth_multipliers(
        f"{kind}_age_multiplier",
        age_labels,
        solution.row_multipliers,
        age_exposure,
        age_priors,
        credibility_k=credibility_k,
        min_exposure=min_exposure,
    )
    tenure_multipliers = _smooth_multipliers(
        f"{kind}_tenure_multiplier",
        tenure_labels,
        solution.col_multipliers,
        tenure_exposure,
        tenure_priors,
        credibility_k=credibility_k,
        min_exposure=min_exposure,
    )

    return HazardFit(
        kind=kind,
        base_rate=base,
        age_multipliers=age_multipliers,
        tenure_multipliers=tenure_multipliers,
        level_constants=dict(priors.level_constants),
        total_events=total_events,
        total_exposure=total_exposure,
        converged=solution.converged,
        iterations=solution.iterations,
    )


def _smooth_multipliers(
    prefix: str,
    labels: Sequence[str],
    fitted: dict[str, float],
    exposure: dict[str, float],
    priors: dict[str, float],
    *,
    credibility_k: float,
    min_exposure: float,
) -> dict[str, FittedValue]:
    return {
        label: FittedValue.from_credibility(
            f"{prefix}[{label}]",
            shrink_ratio(
                fitted.get(label),
                exposure.get(label, 0.0),
                priors[label],
                credibility_k=credibility_k,
                min_exposure=min_exposure,
            ),
        )
        for label in labels
    }


def load_cells(
    conn: "duckdb.DuckDBPyConnection", table: str, event_predicate: str
) -> list[CellObservation]:
    """Aggregate the transition table into age x tenure x level cells."""
    rows = conn.execute(
        f"""
        SELECT age_band, tenure_band, level_id,
               COUNT(*) AS exposure,
               SUM(CASE WHEN {event_predicate} THEN 1 ELSE 0 END) AS events
        FROM {table}
        GROUP BY age_band, tenure_band, level_id
        ORDER BY age_band, tenure_band, level_id
        """
    ).fetchall()
    return [
        CellObservation(
            age_band=str(row[0]),
            tenure_band=str(row[1]),
            level_id=int(row[2]),
            exposure=float(row[3]),
            events=float(row[4] or 0.0),
        )
        for row in rows
    ]


def fit_termination_hazard(
    transitions: TransitionSet,
    priors: HazardPriors,
    *,
    credibility_k: float,
    min_exposure: float,
) -> tuple[HazardFit, list[CellObservation]]:
    """Fit the experienced-cohort termination hazard.

    New hires are excluded by construction: the exposure is the population
    active at the end of the prior year, matching the E077 cohort split.
    """
    cells = load_cells(transitions.conn, transitions.table, "terminated")
    fit = fit_hazard(
        "termination",
        cells,
        priors,
        transitions.bands,
        level_factor=termination_level_factor,
        credibility_k=credibility_k,
        min_exposure=min_exposure,
    )
    return fit, cells


def fit_promotion_hazard(
    transitions: TransitionSet,
    priors: HazardPriors,
    *,
    credibility_k: float,
    min_exposure: float,
) -> tuple[HazardFit, list[CellObservation]]:
    """Fit the promotion hazard over employees who survived the year."""
    cells = load_cells(
        transitions.conn,
        f"(SELECT * FROM {transitions.table} WHERE continued)",
        "promoted",
    )
    fit = fit_hazard(
        "promotion",
        cells,
        priors,
        transitions.bands,
        level_factor=promotion_level_factor,
        credibility_k=credibility_k,
        min_exposure=min_exposure,
    )
    return fit, cells


def fit_scalar_rate(
    conn: "duckdb.DuckDBPyConnection",
    name: str,
    table: str,
    event_predicate: str,
    prior: float,
    *,
    credibility_k: float,
    min_exposure: float,
    where: Optional[str] = None,
) -> FittedValue:
    """Fit one population-level rate (events over exposure)."""
    clause = f"WHERE {where}" if where else ""
    row = conn.execute(
        f"""
        SELECT COUNT(*), SUM(CASE WHEN {event_predicate} THEN 1 ELSE 0 END)
        FROM {table} {clause}
        """
    ).fetchone()
    if row is None:
        raise TransitionError(f"Could not calculate scalar rate '{name}'.")
    exposure, events = row
    return FittedValue.from_credibility(
        name,
        shrink_toward(
            float(events or 0.0),
            float(exposure or 0.0),
            prior,
            credibility_k=credibility_k,
            min_exposure=min_exposure,
        ),
    )
