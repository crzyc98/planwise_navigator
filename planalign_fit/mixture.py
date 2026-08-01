"""A deterministic two-component Gaussian mixture, fitted by EM.

Pure numerics with no domain knowledge, standing to :mod:`planalign_fit.promotion`
as :mod:`planalign_fit.ipf` stands to :mod:`planalign_fit.hazards`. The caller
supplies a sample and a guess at where each component sits; this returns the
fitted components, each observation's posterior probability of belonging to the
second one, and the statistics needed to judge whether the two are actually
distinguishable.

Two properties are load-bearing for the caller:

**Determinism.** There is no RNG here. Initialisation comes from the caller's
guesses, the iteration cap and tolerance are fixed, and the E and M steps are
vectorised reductions. The same input yields bit-identical output, which a
content-hashed parameter pack depends on — random restarts, the usual remedy
for EM's local optima, would change a pack's fingerprint on every run of the
same census.

**Fixed component identity.** Component two is initialised at the higher guess
and a floor keeps it there, so it stays the "upper" component throughout. The
label-switching problem that normally dogs mixture fitting therefore never
arises and no relabelling pass is needed.

The fit is performed on ``log(1 + value)``: raises compound multiplicatively and
are right-skewed, so that is the scale on which a Gaussian is a fair
description. Reported means are transformed back.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

# Fixed convergence controls. Not configurable: see the module docstring.
MAX_ITERATIONS = 200
CONVERGENCE_TOLERANCE = 1e-8

# Keeps a component from collapsing onto a single point (a pay-freeze spike, or
# a handful of identical raises), which would send its density to infinity and
# its standardized distance to a division by zero.
MIN_SIGMA = 1e-4

# Below this a sample cannot support two components on any reading.
MIN_SAMPLE_SIZE = 20


@dataclass(frozen=True)
class MixtureComponent:
    """One fitted component, on the original (not log) scale."""

    mean: float
    sigma: float
    weight: float


@dataclass(frozen=True)
class MixtureFit:
    """A fitted two-component mixture and the evidence for believing it."""

    ordinary: MixtureComponent
    promotion: MixtureComponent
    responsibilities: np.ndarray
    log_likelihood: float
    iterations: int
    converged: bool
    bic: float
    single_bic: float
    standardized_distance: float

    @property
    def bic_improvement(self) -> float:
        """How much better two components are than one. Positive means better."""
        return self.single_bic - self.bic


def _log_normal_density(values: np.ndarray, mean: float, sigma: float) -> np.ndarray:
    sigma = max(sigma, MIN_SIGMA)
    return -0.5 * (
        np.log(2.0 * math.pi) + 2.0 * math.log(sigma) + ((values - mean) / sigma) ** 2
    )


def single_component_bic(values: np.ndarray) -> float:
    """BIC of the one-Gaussian explanation, the null this fit must beat."""
    sample = np.log1p(np.asarray(values, dtype=float))
    if sample.size == 0:
        return math.inf
    mean = float(sample.mean())
    sigma = max(float(sample.std()), MIN_SIGMA)
    log_likelihood = float(_log_normal_density(sample, mean, sigma).sum())
    # Two free parameters: mean and sigma.
    return 2.0 * math.log(sample.size) - 2.0 * log_likelihood


def fit_two_component(
    values: np.ndarray,
    *,
    ordinary_guess: float,
    promotion_guess: float,
) -> Optional[MixtureFit]:
    """Fit two Gaussians to ``log(1 + values)``, anchored at the given guesses.

    ``ordinary_guess`` and ``promotion_guess`` are decimal growth rates (0.05
    for a 5% raise). They set where EM starts and which component is which;
    they do not constrain where it finishes. Returns ``None`` when the sample
    is too small to fit at all.
    """
    sample = np.log1p(np.asarray(values, dtype=float))
    if sample.size < MIN_SAMPLE_SIZE:
        return None

    lower = math.log1p(min(ordinary_guess, promotion_guess))
    upper = math.log1p(max(ordinary_guess, promotion_guess))
    spread = max(float(sample.std()), MIN_SIGMA)

    means = np.array([lower, upper], dtype=float)
    # The upper component is the rarer one and starts wider; the exact values
    # matter little, only that the two start apart and in a fixed order.
    sigmas = np.array([spread * 0.5, spread], dtype=float)
    weights = np.array([0.9, 0.1], dtype=float)

    previous = -math.inf
    log_likelihood = -math.inf
    responsibilities = np.zeros_like(sample)
    converged = False
    iterations = 0
    # Set when EM cannot keep two live components. The parameters then still
    # hold their initial guesses, which are the caller's priors rather than
    # anything the data said — reporting a separation from them would
    # manufacture evidence out of an initialisation.
    abandoned = float(sample.std()) <= MIN_SIGMA

    for iterations in range(1, MAX_ITERATIONS + 1):
        # E step, in log space so a far-out observation cannot underflow to a
        # zero denominator and produce a NaN responsibility.
        log_components = np.vstack(
            [
                math.log(max(weights[k], 1e-300))
                + _log_normal_density(sample, means[k], sigmas[k])
                for k in range(2)
            ]
        )
        peak = log_components.max(axis=0)
        stabilized = np.exp(log_components - peak)
        total = stabilized.sum(axis=0)
        responsibilities = stabilized[1] / total
        log_likelihood = float((peak + np.log(total)).sum())

        # M step.
        upper_mass = float(responsibilities.sum())
        lower_mass = float(sample.size - upper_mass)
        if upper_mass <= 0.0 or lower_mass <= 0.0:
            # One component has been abandoned; there is nothing to separate.
            abandoned = True
            break

        weights = np.array(
            [lower_mass / sample.size, upper_mass / sample.size], dtype=float
        )
        means = np.array(
            [
                float(((1.0 - responsibilities) * sample).sum() / lower_mass),
                float((responsibilities * sample).sum() / upper_mass),
            ]
        )
        sigmas = np.array(
            [
                math.sqrt(
                    max(
                        float(
                            ((1.0 - responsibilities) * (sample - means[0]) ** 2).sum()
                            / lower_mass
                        ),
                        MIN_SIGMA**2,
                    )
                ),
                math.sqrt(
                    max(
                        float(
                            (responsibilities * (sample - means[1]) ** 2).sum()
                            / upper_mass
                        ),
                        MIN_SIGMA**2,
                    )
                ),
            ]
        )

        if abs(log_likelihood - previous) < CONVERGENCE_TOLERANCE:
            converged = True
            break
        previous = log_likelihood

    # Five free parameters: two means, two sigmas, one mixing weight.
    bic = 5.0 * math.log(sample.size) - 2.0 * log_likelihood
    if abandoned:
        # No two-component solution was reached, so there is no separation to
        # report and nothing for the caller to prefer over a single component.
        distance = 0.0
        bic = math.inf
    else:
        pooled = math.sqrt(
            float(weights[0] * sigmas[0] ** 2 + weights[1] * sigmas[1] ** 2)
        )
        distance = abs(means[1] - means[0]) / max(pooled, MIN_SIGMA)

    return MixtureFit(
        ordinary=MixtureComponent(
            mean=float(math.expm1(means[0])),
            sigma=float(sigmas[0]),
            weight=float(weights[0]),
        ),
        promotion=MixtureComponent(
            mean=float(math.expm1(means[1])),
            sigma=float(sigmas[1]),
            weight=float(weights[1]),
        ),
        responsibilities=responsibilities,
        log_likelihood=log_likelihood,
        iterations=iterations,
        converged=converged,
        bic=bic,
        single_bic=single_component_bic(values),
        standardized_distance=float(distance),
    )
