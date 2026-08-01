"""Tests for the two-component raise mixture behind the promotion fit (#511).

These grade the estimator in isolation, on arrays drawn from known parameters,
with no census and no DuckDB. The census-level round trip lives in
``test_parameter_fitting.py``; what is checked here is the numerical core:
does EM recover the components, does it refuse to separate what genuinely
overlaps, and is it deterministic enough to sit behind a content-hashed
parameter pack.
"""

from __future__ import annotations

import math
import random

import numpy as np
import pytest

from planalign_fit.mixture import (
    MAX_ITERATIONS,
    fit_two_component,
    single_component_bic,
)

pytestmark = pytest.mark.fast


def draw(
    n: int,
    *,
    ordinary_centre: float,
    ordinary_sigma: float,
    promotion_centre: float,
    promotion_sigma: float,
    promotion_share: float,
    seed: int = 11,
) -> np.ndarray:
    """Growth values from a known two-component mixture.

    Uses ``random.Random`` rather than numpy's generator so the sample is
    reproducible across numpy versions.
    """
    rng = random.Random(seed)
    values = []
    for _ in range(n):
        if rng.random() < promotion_share:
            centre, sigma = promotion_centre, promotion_sigma
        else:
            centre, sigma = ordinary_centre, ordinary_sigma
        values.append(rng.gauss(centre, sigma))
    return np.array(values)


class TestRecovery:
    """EM recovers the parameters a sample was generated from."""

    def test_recovers_the_promotion_share(self):
        values = draw(
            8_000,
            ordinary_centre=0.055,
            ordinary_sigma=0.015,
            promotion_centre=0.18,
            promotion_sigma=0.04,
            promotion_share=0.06,
        )
        fit = fit_two_component(values, ordinary_guess=0.055, promotion_guess=0.20)
        assert fit.promotion.weight == pytest.approx(0.06, abs=0.015)

    def test_recovers_both_component_centres(self):
        values = draw(
            8_000,
            ordinary_centre=0.055,
            ordinary_sigma=0.015,
            promotion_centre=0.18,
            promotion_sigma=0.04,
            promotion_share=0.06,
        )
        fit = fit_two_component(values, ordinary_guess=0.055, promotion_guess=0.20)
        assert fit.ordinary.mean == pytest.approx(0.055, abs=0.01)
        assert fit.promotion.mean == pytest.approx(0.18, abs=0.02)

    def test_responsibilities_are_probabilities(self):
        values = draw(
            2_000,
            ordinary_centre=0.05,
            ordinary_sigma=0.02,
            promotion_centre=0.20,
            promotion_sigma=0.04,
            promotion_share=0.10,
        )
        fit = fit_two_component(values, ordinary_guess=0.05, promotion_guess=0.20)
        assert fit.responsibilities.shape == values.shape
        assert fit.responsibilities.min() >= 0.0
        assert fit.responsibilities.max() <= 1.0

    def test_large_raises_get_high_responsibility(self):
        """The posterior must point the right way, not merely be in range."""
        values = draw(
            2_000,
            ordinary_centre=0.05,
            ordinary_sigma=0.015,
            promotion_centre=0.20,
            promotion_sigma=0.03,
            promotion_share=0.10,
        )
        fit = fit_two_component(values, ordinary_guess=0.05, promotion_guess=0.20)
        biggest = fit.responsibilities[np.argmax(values)]
        smallest = fit.responsibilities[np.argmin(values)]
        assert biggest > 0.9
        assert smallest < 0.1

    def test_expected_events_match_the_share(self):
        """Summed responsibilities are the expected promotion count."""
        values = draw(
            5_000,
            ordinary_centre=0.05,
            ordinary_sigma=0.015,
            promotion_centre=0.20,
            promotion_sigma=0.03,
            promotion_share=0.08,
            seed=3,
        )
        fit = fit_two_component(values, ordinary_guess=0.05, promotion_guess=0.20)
        assert fit.responsibilities.sum() / values.size == pytest.approx(
            fit.promotion.weight, abs=1e-6
        )


class TestSeparation:
    """The statistics that decide whether a level's verdict is trustworthy."""

    def test_well_separated_components_clear_the_distance_floor(self):
        values = draw(
            5_000,
            ordinary_centre=0.05,
            ordinary_sigma=0.015,
            promotion_centre=0.20,
            promotion_sigma=0.03,
            promotion_share=0.08,
        )
        fit = fit_two_component(values, ordinary_guess=0.05, promotion_guess=0.20)
        assert fit.standardized_distance > 2.0

    def test_overlapping_components_fail_the_distance_floor(self):
        """A promotion step barely above the merit spread is not recoverable."""
        values = draw(
            5_000,
            ordinary_centre=0.05,
            ordinary_sigma=0.04,
            promotion_centre=0.08,
            promotion_sigma=0.04,
            promotion_share=0.10,
        )
        fit = fit_two_component(values, ordinary_guess=0.05, promotion_guess=0.20)
        assert fit.standardized_distance < 2.0

    def test_single_population_is_not_preferred_as_two_components(self):
        """One Gaussian must not be split into two by BIC."""
        rng = random.Random(5)
        values = np.array([rng.gauss(0.05, 0.02) for _ in range(4_000)])
        fit = fit_two_component(values, ordinary_guess=0.05, promotion_guess=0.20)
        assert fit.bic_improvement <= 0.0 or fit.standardized_distance < 2.0

    def test_genuine_mixture_is_preferred_over_one_component(self):
        values = draw(
            5_000,
            ordinary_centre=0.05,
            ordinary_sigma=0.015,
            promotion_centre=0.20,
            promotion_sigma=0.03,
            promotion_share=0.08,
        )
        fit = fit_two_component(values, ordinary_guess=0.05, promotion_guess=0.20)
        assert fit.bic_improvement > 0.0

    def test_single_component_bic_is_finite_for_a_normal_sample(self):
        rng = random.Random(9)
        values = np.array([rng.gauss(0.05, 0.02) for _ in range(500)])
        assert math.isfinite(single_component_bic(values))


class TestDeterminism:
    """A content-hashed pack cannot sit on a nondeterministic estimator."""

    @staticmethod
    def _sample() -> np.ndarray:
        return draw(
            3_000,
            ordinary_centre=0.05,
            ordinary_sigma=0.015,
            promotion_centre=0.20,
            promotion_sigma=0.03,
            promotion_share=0.08,
            seed=42,
        )

    def test_repeated_fits_are_bit_identical(self):
        values = self._sample()
        first = fit_two_component(values, ordinary_guess=0.05, promotion_guess=0.20)
        second = fit_two_component(values, ordinary_guess=0.05, promotion_guess=0.20)
        assert first.promotion.weight == second.promotion.weight
        assert first.ordinary.mean == second.ordinary.mean
        assert first.log_likelihood == second.log_likelihood
        assert np.array_equal(first.responsibilities, second.responsibilities)

    def test_row_order_does_not_change_the_fit(self):
        """Transitions arrive in whatever order SQL returns them."""
        values = self._sample()
        shuffled = values.copy()
        random.Random(7).shuffle(shuffled)

        original = fit_two_component(values, ordinary_guess=0.05, promotion_guess=0.20)
        reordered = fit_two_component(
            shuffled, ordinary_guess=0.05, promotion_guess=0.20
        )
        assert original.promotion.weight == pytest.approx(
            reordered.promotion.weight, abs=1e-12
        )
        assert original.ordinary.mean == pytest.approx(
            reordered.ordinary.mean, abs=1e-12
        )

    def test_component_identity_never_switches(self):
        """Promotion is always the higher-location component, by construction."""
        for seed in range(5):
            values = draw(
                1_500,
                ordinary_centre=0.05,
                ordinary_sigma=0.02,
                promotion_centre=0.20,
                promotion_sigma=0.04,
                promotion_share=0.10,
                seed=seed,
            )
            fit = fit_two_component(values, ordinary_guess=0.05, promotion_guess=0.20)
            assert fit.promotion.mean > fit.ordinary.mean


class TestPriorEscape:
    """Anchoring EM at the configured prior must not pin the answer to it.

    This is the stated risk of a deterministic, prior-initialised EM: it buys
    reproducibility, but it must not buy it by refusing to move.
    """

    def test_recovers_a_truth_far_from_the_initial_guess(self):
        values = draw(
            8_000,
            ordinary_centre=0.09,
            ordinary_sigma=0.015,
            promotion_centre=0.32,
            promotion_sigma=0.04,
            promotion_share=0.12,
            seed=17,
        )
        # Initialised at values well away from the truth on both components.
        fit = fit_two_component(values, ordinary_guess=0.03, promotion_guess=0.15)
        assert fit.ordinary.mean == pytest.approx(0.09, abs=0.015)
        assert fit.promotion.mean == pytest.approx(0.32, abs=0.03)
        assert fit.promotion.weight == pytest.approx(0.12, abs=0.02)

    def test_recovers_a_rate_far_below_the_prior(self):
        values = draw(
            8_000,
            ordinary_centre=0.05,
            ordinary_sigma=0.015,
            promotion_centre=0.20,
            promotion_sigma=0.03,
            promotion_share=0.01,
            seed=23,
        )
        fit = fit_two_component(values, ordinary_guess=0.05, promotion_guess=0.20)
        assert fit.promotion.weight == pytest.approx(0.01, abs=0.01)


class TestDegenerateInput:
    """Real censuses contain pay freezes, tiny levels, and constant raises."""

    def test_empty_input_does_not_raise(self):
        fit = fit_two_component(np.array([]), ordinary_guess=0.05, promotion_guess=0.20)
        assert fit is None

    def test_constant_input_does_not_divide_by_zero(self):
        values = np.full(500, 0.055)
        fit = fit_two_component(values, ordinary_guess=0.05, promotion_guess=0.20)
        if fit is not None:
            assert math.isfinite(fit.standardized_distance)
            assert fit.standardized_distance < 2.0

    def test_tiny_sample_does_not_raise(self):
        values = np.array([0.05, 0.06, 0.19])
        fit = fit_two_component(values, ordinary_guess=0.05, promotion_guess=0.20)
        if fit is not None:
            assert 0.0 <= fit.promotion.weight <= 1.0

    def test_iteration_cap_is_respected(self):
        values = draw(
            1_000,
            ordinary_centre=0.05,
            ordinary_sigma=0.02,
            promotion_centre=0.20,
            promotion_sigma=0.04,
            promotion_share=0.08,
        )
        fit = fit_two_component(values, ordinary_guess=0.05, promotion_guess=0.20)
        assert fit.iterations <= MAX_ITERATIONS
