"""Fit enrollment and deferral behaviour from observed participation changes.

The simulator decides voluntary enrollment in
``int_voluntary_enrollment_decision`` with a two-factor model::

    P(enroll) = base_rates_by_age[age_segment] * income_multipliers[income_segment]
                * job_level_multipliers[level_segment]

over exactly the population a census diff exposes: employees who were not
participating and were not auto-enrolled. So that is what gets fitted, with the
same exposure-weighted IPF as the hazards.

Which population is at risk depends on auto-enrollment:

============================  ==========================  =====================
``auto_enrollment``           voluntary exposure           opt-out fit
============================  ==========================  =====================
disabled                      continuing + new hires      not applicable
enabled, ``new_hires_only``   continuing only             new hires (proxy)
enabled, all eligible         nothing                     everyone (proxy)
============================  ==========================  =====================

``job_level_multipliers`` are deliberately not fitted: level is assigned from
compensation, so it is near-collinear with the income segment and a short
census history cannot separate the two.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from planalign_fit import ipf
from planalign_fit.bands import AGE_SEGMENTS, INCOME_SEGMENTS
from planalign_fit.models import FittedValue, Unfittable
from planalign_fit.priors import Priors
from planalign_fit.smoothing import shrink_ratio, shrink_toward
from planalign_fit.transitions import TransitionSet

if TYPE_CHECKING:  # pragma: no cover - typing only
    import duckdb

VOLUNTARY_PREFIX = "enrollment.voluntary_enrollment"
OPT_OUT_TARGET_KEY = "enrollment.auto_enrollment.opt_out_rates.target"

ALL_ELIGIBLE_SCOPE = "all_eligible_employees"


@dataclass(frozen=True)
class SegmentFit:
    """A fitted two-factor participation model over age x income segments."""

    base_rates_by_age: dict[str, FittedValue]
    income_multipliers: dict[str, FittedValue]
    total_events: float
    total_exposure: float

    def values(self) -> list[FittedValue]:
        return [*self.base_rates_by_age.values(), *self.income_multipliers.values()]


@dataclass(frozen=True)
class AutoEnrollmentPosture:
    """How auto-enrollment shapes what the census can identify."""

    enabled: bool
    scope: str

    @property
    def covers_new_hires(self) -> bool:
        return self.enabled

    @property
    def covers_continuing(self) -> bool:
        return self.enabled and self.scope == ALL_ELIGIBLE_SCOPE


def auto_enrollment_posture(priors: Priors) -> AutoEnrollmentPosture:
    return AutoEnrollmentPosture(
        enabled=bool(priors.config_value("enrollment.auto_enrollment.enabled", False)),
        scope=str(
            priors.config_value("enrollment.auto_enrollment.scope", "new_hires_only")
        ),
    )


def _segment_cells(
    conn: "duckdb.DuckDBPyConnection", sources: list[tuple[str, str, str]]
) -> list[ipf.FactorCell]:
    """Aggregate one or more (table, event, filter) sources into segment cells.

    Sources are unioned before grouping so a single fit can span the continuing
    and new-hire populations, which live in different tables.
    """
    unioned = "\nUNION ALL\n".join(
        f"SELECT age_segment, income_segment, "
        f"CASE WHEN {event} THEN 1 ELSE 0 END AS event "
        f"FROM {table} WHERE {where}"
        for table, event, where in sources
    )
    rows = conn.execute(
        f"""
        SELECT age_segment, income_segment, COUNT(*) AS exposure, SUM(event) AS events
        FROM ({unioned})
        GROUP BY age_segment, income_segment
        """
    ).fetchall()
    return [
        ipf.FactorCell(
            row=str(row[0]),
            col=str(row[1]),
            exposure=float(row[2]),
            events=float(row[3] or 0.0),
        )
        for row in rows
    ]


def _fit_segments(
    cells: list[ipf.FactorCell],
    age_priors: dict[str, float],
    income_priors: dict[str, float],
    *,
    prefix: str,
    credibility_k: float,
    min_exposure: float,
) -> SegmentFit:
    """Fit base-by-age x income-multiplier, normalizing the income axis to 1.0.

    Normalizing income means ``base * row_multiplier`` is directly the age
    segment's base rate — the number the config stores.
    """
    solution = ipf.solve(cells, AGE_SEGMENTS, INCOME_SEGMENTS, normalize="col")
    age_exposure = ipf.exposure_by(cells, "row")
    income_exposure = ipf.exposure_by(cells, "col")
    fitted_anything = solution.base > 0

    base_rates = {
        segment: FittedValue.from_credibility(
            f"{prefix}.base_rates_by_age.{segment}",
            shrink_ratio(
                solution.base * solution.row_multipliers[segment]
                if fitted_anything
                else None,
                age_exposure.get(segment, 0.0),
                age_priors[segment],
                credibility_k=credibility_k,
                min_exposure=min_exposure,
            ),
        )
        for segment in AGE_SEGMENTS
    }
    income_multipliers = {
        segment: FittedValue.from_credibility(
            f"{prefix}.income_multipliers.{segment}",
            shrink_ratio(
                solution.col_multipliers.get(segment) if fitted_anything else None,
                income_exposure.get(segment, 0.0),
                income_priors[segment],
                credibility_k=credibility_k,
                min_exposure=min_exposure,
            ),
        )
        for segment in INCOME_SEGMENTS
    }

    return SegmentFit(
        base_rates_by_age=base_rates,
        income_multipliers=income_multipliers,
        total_events=sum(cell.events for cell in cells),
        total_exposure=sum(cell.exposure for cell in cells),
    )


def _segment_priors(
    priors: Priors,
    path: str,
    segments: tuple[str, ...],
    default: float,
) -> dict[str, float]:
    resolved: dict[str, float] = {}
    for segment in segments:
        value = priors.config_value(f"{path}.{segment}")
        try:
            resolved[segment] = float(value)
        except (TypeError, ValueError):
            resolved[segment] = default
    return resolved


def voluntary_enrollment_sources(
    transitions: TransitionSet, posture: AutoEnrollmentPosture
) -> list[tuple[str, str, str]]:
    """The at-risk populations for a voluntary enrollment fit."""
    sources: list[tuple[str, str, str]] = []
    if not posture.covers_continuing:
        sources.append(
            (
                transitions.table,
                "to_enrolled",
                "continued AND from_enrolled IS NOT NULL AND NOT from_enrolled",
            )
        )
    if not posture.covers_new_hires:
        sources.append(
            (
                transitions.new_hires_table,
                "is_enrolled",
                "is_active AND is_enrolled IS NOT NULL",
            )
        )
    return sources


def fit_voluntary_enrollment(
    transitions: TransitionSet,
    priors: Priors,
    posture: AutoEnrollmentPosture,
    *,
    credibility_k: float,
    min_exposure: float,
) -> Optional[SegmentFit]:
    """Fit voluntary enrollment over whoever auto-enrollment did not cover."""
    sources = voluntary_enrollment_sources(transitions, posture)
    if not sources:
        return None
    return _fit_segments(
        _segment_cells(transitions.conn, sources),
        _segment_priors(
            priors, f"{VOLUNTARY_PREFIX}.base_rates_by_age", AGE_SEGMENTS, 0.5
        ),
        _segment_priors(
            priors, f"{VOLUNTARY_PREFIX}.income_multipliers", INCOME_SEGMENTS, 1.0
        ),
        prefix=VOLUNTARY_PREFIX,
        credibility_k=credibility_k,
        min_exposure=min_exposure,
    )


def fit_opt_out_target(
    transitions: TransitionSet,
    priors: Priors,
    posture: AutoEnrollmentPosture,
    *,
    credibility_k: float,
    min_exposure: float,
) -> Optional[FittedValue]:
    """Fit the overall opt-out rate as first-year non-participation.

    The typed config exposes a single ``target`` and derives demographic rates
    from it (``OPT_OUT_AGE_MULTIPLIERS``), so one scalar is what the simulator
    consumes. This is a *proxy*: the census records participation, not who was
    auto-enrolled and then opted out.
    """
    if not posture.covers_new_hires:
        return None
    row = transitions.conn.execute(
        f"""
        SELECT COUNT(*), SUM(CASE WHEN NOT is_enrolled THEN 1 ELSE 0 END)
        FROM {transitions.new_hires_table}
        WHERE is_active AND is_enrolled IS NOT NULL
        """
    ).fetchone()
    if row is None:
        return None
    exposure, opted_out = row
    if not exposure:
        return None
    return FittedValue.from_credibility(
        OPT_OUT_TARGET_KEY,
        shrink_toward(
            float(opted_out or 0.0),
            float(exposure),
            float(priors.config_value(OPT_OUT_TARGET_KEY, 0.09) or 0.09),
            credibility_k=credibility_k,
            min_exposure=min_exposure,
        ),
    )


def fit_default_deferral_rates(
    transitions: TransitionSet,
    priors: Priors,
    *,
    credibility_k: float,
    min_exposure: float,
) -> dict[tuple[str, str], FittedValue]:
    """Fit the starting deferral rate of newly enrolled employees per segment.

    The population is everyone observed enrolling this year — continuing
    converts plus first-year new hires — because both pick a starting rate the
    same way.
    """
    rows = transitions.conn.execute(
        f"""
        WITH newly_enrolled AS (
          SELECT age_segment, income_segment, to_deferral_rate AS deferral_rate
          FROM {transitions.table}
          WHERE continued AND to_enrolled AND NOT COALESCE(from_enrolled, FALSE)
          UNION ALL
          SELECT age_segment, income_segment, deferral_rate
          FROM {transitions.new_hires_table}
          WHERE is_active AND is_enrolled
        )
        SELECT age_segment, income_segment,
               MEDIAN(deferral_rate) AS median_rate,
               COUNT(deferral_rate) AS exposure
        FROM newly_enrolled
        WHERE deferral_rate IS NOT NULL AND deferral_rate > 0
        GROUP BY age_segment, income_segment
        """
    ).fetchall()
    observed = {
        (str(row[0]), str(row[1])): (float(row[2]), float(row[3]))
        for row in rows
        if row[2] is not None
    }

    fitted: dict[tuple[str, str], FittedValue] = {}
    for age_segment in AGE_SEGMENTS:
        for income_segment in INCOME_SEGMENTS:
            key = (age_segment, income_segment)
            median_rate, exposure = observed.get(key, (None, 0.0))
            prior = priors.deferral_rates.get(key, 0.03)
            fitted[key] = FittedValue.from_credibility(
                f"default_deferral_rate[{age_segment}/{income_segment}]",
                shrink_ratio(
                    median_rate,
                    exposure,
                    prior,
                    credibility_k=credibility_k,
                    min_exposure=min_exposure,
                ),
            )
    return fitted


@dataclass(frozen=True)
class EscalationFit:
    """Observed deferral escalation among employees enrolled in both years."""

    increment_amount: FittedValue
    adoption_rate: float
    exposure: float


def fit_escalation(
    transitions: TransitionSet,
    priors: Priors,
    *,
    credibility_k: float,
    min_exposure: float,
) -> Optional[EscalationFit]:
    """Fit the annual escalation increment and measure its adoption.

    ``deferral_auto_escalation.enabled`` is a switch, not a rate, so adoption is
    reported as evidence for that switch rather than written into the pack.
    """
    row = transitions.conn.execute(
        f"""
        SELECT COUNT(*),
               SUM(CASE WHEN to_deferral_rate > from_deferral_rate THEN 1 ELSE 0 END),
               MEDIAN(CASE WHEN to_deferral_rate > from_deferral_rate
                           THEN to_deferral_rate - from_deferral_rate END)
        FROM {transitions.table}
        WHERE continued
          AND COALESCE(from_enrolled, FALSE)
          AND from_deferral_rate IS NOT NULL
          AND to_deferral_rate IS NOT NULL
        """
    ).fetchone()
    if row is None:
        return None
    exposure, escalated, median_increase = row

    exposure = float(exposure or 0.0)
    if exposure <= 0:
        return None

    escalated = float(escalated or 0.0)
    prior = float(
        priors.config_value("deferral_auto_escalation.increment_amount", 0.01) or 0.01
    )
    return EscalationFit(
        increment_amount=FittedValue.from_credibility(
            "deferral_auto_escalation.increment_amount",
            shrink_ratio(
                float(median_increase) if median_increase is not None else None,
                escalated,
                prior,
                credibility_k=credibility_k,
                min_exposure=min_exposure,
            ),
        ),
        adoption_rate=escalated / exposure,
        exposure=exposure,
    )


def match_response_unfittable(priors: Priors) -> Unfittable:
    """Match response needs a match-formula change to identify; a census lacks one."""
    return Unfittable(
        name="deferral_match_response.*",
        reason=(
            "identifying a match response needs a change in the match formula "
            "inside the observation window; a census carries deferral rates but "
            "not the plan's match schedule, so the response cannot be separated "
            "from ordinary deferral drift"
        ),
        default_used=priors.config_value("deferral_match_response", {}),
    )


def job_level_multipliers_unfittable() -> Unfittable:
    return Unfittable(
        name=f"{VOLUNTARY_PREFIX}.job_level_multipliers.*",
        reason=(
            "job level is assigned from compensation, so it is near-collinear "
            "with the income segment; a short census history cannot separate the "
            "two effects"
        ),
        default_used="base config value",
    )
