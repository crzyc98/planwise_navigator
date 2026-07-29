"""Credibility smoothing so thin cells never turn noise into a parameter.

A cell's fitted value is a credibility-weighted blend of what the data says and
a prior — the current seed value, or a pooled estimate from the parent grouping
when the cell is too thin to trust on its own:

    Z = exposure / (exposure + k)
    fitted = Z * observed + (1 - Z) * prior

``k`` is the exposure at which the data and the prior carry equal weight. Cells
below ``min_exposure`` are labelled ``pooled`` so the fit report can call them
out explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Basis = Literal["observed", "blended", "pooled", "prior"]

# Above this credibility the estimate is essentially the data's own.
OBSERVED_CREDIBILITY_THRESHOLD = 0.80

DEFAULT_CREDIBILITY_K = 200.0
DEFAULT_MIN_EXPOSURE = 50.0


@dataclass(frozen=True)
class CredibilityResult:
    """A smoothed estimate with the evidence behind it."""

    value: float
    observed: Optional[float]
    events: float
    exposure: float
    prior: float
    credibility: float
    basis: Basis

    @property
    def is_thin(self) -> bool:
        return self.basis in ("pooled", "prior")

    def note(self) -> str:
        if self.basis == "prior":
            return "no exposure — prior retained"
        if self.basis == "pooled":
            return (
                f"thin cell ({self.exposure:,.0f} exposure) — "
                f"{(1 - self.credibility):.0%} weight on the pooled prior"
            )
        if self.basis == "blended":
            return f"{self.credibility:.0%} weight on observed data"
        return "fitted from data"


def shrink_toward(
    events: float,
    exposure: float,
    prior: float,
    *,
    credibility_k: float = DEFAULT_CREDIBILITY_K,
    min_exposure: float = DEFAULT_MIN_EXPOSURE,
) -> CredibilityResult:
    """Blend the observed rate ``events / exposure`` toward ``prior``."""
    if exposure <= 0:
        return CredibilityResult(
            value=prior,
            observed=None,
            events=events,
            exposure=exposure,
            prior=prior,
            credibility=0.0,
            basis="prior",
        )

    observed = events / exposure
    credibility = exposure / (exposure + credibility_k) if credibility_k > 0 else 1.0
    value = credibility * observed + (1.0 - credibility) * prior

    if exposure < min_exposure:
        basis: Basis = "pooled"
    elif credibility >= OBSERVED_CREDIBILITY_THRESHOLD:
        basis = "observed"
    else:
        basis = "blended"

    return CredibilityResult(
        value=value,
        observed=observed,
        events=events,
        exposure=exposure,
        prior=prior,
        credibility=credibility,
        basis=basis,
    )


def shrink_ratio(
    observed: Optional[float],
    exposure: float,
    prior: float,
    *,
    credibility_k: float = DEFAULT_CREDIBILITY_K,
    min_exposure: float = DEFAULT_MIN_EXPOSURE,
) -> CredibilityResult:
    """Credibility-blend an already-computed ratio (e.g. a hazard multiplier).

    Same weighting as :func:`shrink_toward`, but for estimates that are not a
    plain event count over an exposure — a fitted multiplier, a median raise.
    """
    if exposure <= 0 or observed is None:
        return CredibilityResult(
            value=prior,
            observed=observed,
            events=0.0,
            exposure=max(exposure, 0.0),
            prior=prior,
            credibility=0.0,
            basis="prior",
        )

    credibility = exposure / (exposure + credibility_k) if credibility_k > 0 else 1.0
    value = credibility * observed + (1.0 - credibility) * prior

    if exposure < min_exposure:
        basis: Basis = "pooled"
    elif credibility >= OBSERVED_CREDIBILITY_THRESHOLD:
        basis = "observed"
    else:
        basis = "blended"

    return CredibilityResult(
        value=value,
        observed=observed,
        events=0.0,
        exposure=exposure,
        prior=prior,
        credibility=credibility,
        basis=basis,
    )
