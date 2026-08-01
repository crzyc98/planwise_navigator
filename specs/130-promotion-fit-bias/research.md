# Phase 0 Research — Promotion Fit Bias

**Feature**: 130-promotion-fit-bias | **Date**: 2026-08-01

Issue #511 posed four candidate approaches and explicitly declined to pick one. This document picks one and records why the other three lost.

---

## R-1: Estimator choice

**Decision**: A **two-component Gaussian mixture on `log(1 + compensation_growth)`, fitted per job level by EM**.

**Rationale**:

The simulator generates a continued employee's raise one of two ways — `cola + merit_base[level]` for an ordinary year, or `promotion_compensation.base_increase_pct` (0.20, `config/simulation_config.yaml:37`) with `distribution_range` (±0.05) for a promotion year. That is *literally* a two-component mixture, so fitting one back is not an approximation of the client's behavior; it is the inverse of the generative model the simulator already commits to. No extra census column is needed, satisfying FR-014.

Log space rather than raw growth: raises compound multiplicatively and their distribution is right-skewed, so `log(1+g)` is the scale on which a Gaussian is a reasonable description. It also makes the ordinary component's location directly interpretable as a rate once exponentiated.

Per level rather than pooled: merit is already a per-level parameter (`comp_levers.csv`, `merit_base`), so the ordinary component's location genuinely differs by level. Pooling would manufacture a spurious second mode out of the between-level spread in merit alone — the same category of error this feature exists to fix.

**Alternatives considered**:

| Option (from #511) | Why rejected |
|---|---|
| **(2) Joint identification of merit and promotion** | Not rejected — **subsumed**. The mixture *is* a joint identification: EM estimates the ordinary component's location (→ merit) and the promotion component's weight (→ hazard) in the same pass, off the same likelihood. Treating (1) and (2) as alternatives was the issue's framing; in practice choosing (1) delivers (2) for free, which is what makes the circularity objection go away rather than merely move. |
| **(3) Require `level_id`; mark promotion unfittable without it** | Retained as the **fallback**, not the primary. Resolved in spec clarification: FR-004 makes it the per-level outcome when the mixture does not separate. As the primary it would concede that a level-less census can never yield a promotion rate, which is a large capability loss for the common case. |
| **(4) Detect the bias and report a plausible range** | Rejected in spec clarification. A range whose upper end is 16.8% and lower end is 6% does not let an analyst run a projection — they must still pick a number, with no basis for picking. FR-012 removes the current upper-bound framing for the same reason. |
| Threshold rule: "a band crossing counts only if the raise exceeds the merit band" | Rejected by the issue itself, correctly. It defines promotion in terms of merit, while merit is measured off the non-promoted population — the two identify off each other. FR-003 forbids it explicitly. |

---

## R-2: Breaking the circularity

**Decision**: Merit is read off the mixture's **fitted** ordinary component, via posterior responsibilities, never off a prior hard classification.

**Rationale**: The circularity in the current code is structural: `compensation.py:45` filters `WHERE continued AND NOT promoted`, and `promoted` is exactly the quantity under dispute. EM has no such ordering — it converges on both components simultaneously, with each transition contributing to both in proportion to its responsibility. There is no point in the computation where a merit estimate is an input to a promotion classification or vice versa.

The one residual dependence is the *initialization* (R-4), which uses the merit prior to anchor the ordinary component. That is a starting point, not a constraint: EM moves both components freely from there. The mitigation is empirical — a round-trip test where the truth merit sits well away from the seeded prior, asserting recovery anyway. If EM cannot escape the prior, the initialization is wrong and must be fixed; the tolerance must not be widened to hide it.

---

## R-3: The separation test

**Decision**: Two conditions, both required, both fixed constants (FR-016):

1. **BIC prefers two components over one.** `BIC = k·ln(n) − 2·ln(L̂)`, computed for the fitted two-component model and for a single Gaussian on the same data. Two components must win outright.
2. **Standardized separation** `abs(mu_promo − mu_ordinary) / sigma_pooled >= 2.0`, where `sigma_pooled` is the weight-weighted pooled standard deviation of the two components.

A level must also clear the existing `min_exposure` before the test is attempted at all; below that it is `pooled` by the machinery that already handles thin cells.

**Rationale**: The two conditions guard different failures, which is why one is not enough.

BIC alone answers "are there two components?" but not "can I *tell them apart*?" A two-component model can win on BIC while producing posteriors that all sit near 0.5 — technically a better fit, practically a coin flip, which is exactly the outcome the spec's edge case forbids.

The distance floor alone answers the second question but not the first: on thin or noisy data you can always find two well-separated means if you are willing to let one component chase a handful of outliers. BIC's parameter penalty is what stops that.

The 2.0 threshold: at two pooled standard deviations of separation the components' posteriors are decisive for the bulk of the mass, and the classification is meaningfully better than chance. It is a conventional bimodality-detection floor, not a tuned value — and per FR-016 it must stay untuned, since tuning it down until a number appears is precisely the abuse the fixed-constant rule exists to prevent.

**Alternatives considered**: A likelihood-ratio test was rejected because the regularity conditions fail for mixture models (the null sits on the parameter-space boundary), so the χ² reference distribution does not hold and the p-value would be misleading. Bhattacharyya or overlap coefficients were considered and are near-equivalent to the standardized distance for two Gaussians; the distance is chosen for being directly reportable to an analyst in units they can reason about.

---

## R-4: Determinism

**Decision**: No RNG. Deterministic prior-anchored initialization; `max_iter = 200`; convergence tolerance `1e-8` on the log-likelihood change.

Initialization per level:
- Ordinary component: `mu_1 = log(1 + cola[level] + merit_prior[level])`, `sigma_1 = 0.02`
- Promotion component: `mu_2 = log(1 + cola[level] + promotion_base_increase_pct)`, `sigma_2 = 0.05`
- Mixing weight: `pi_2 = promotion_hazard_base_prior`

**Rationale**: Constitution I requires reproducibility, and the parameter pack's fingerprint is a content hash over the fitted values (`pack.py:14`) — a nondeterministic estimator would produce a different fingerprint on every run of the same census, destroying the provenance chain that Feature 109 and #458 built. Random restarts, the usual EM remedy for local optima, are therefore unavailable.

Prior anchoring buys two things beyond determinism. It starts EM in the neighborhood of the answer, which makes local-optimum escape much less of a concern than with random init. And it fixes component *identity* by construction — component 2 starts at the promotion location and stays there — so the label-switching problem that normally plagues mixture fitting simply does not arise, and no post-hoc relabeling step is needed.

The iteration cap doubles as a guard: non-convergence within 200 iterations is recorded and treated as a failed separation for that level, consistent with how `HazardFit.converged` is already surfaced (`report.py:106`).

---

## R-5: Degenerate and out-of-support observations

**Decision**:

| Case | Promotion weight | Promotion exposure | Merit pool |
|---|---|---|---|
| Growth <= 0 (pay cut, freeze, missing) | 0 (forced) | Included | Included, weight 1 |
| Growth outside `[MIN_PLAUSIBLE_GROWTH, MAX_PLAUSIBLE_GROWTH]` (`compensation.py:30-31`) | 0 (forced) | Included | Excluded |
| Employee already at the highest job level | 0 (forced) | Included | Included, weight 1 |
| Otherwise | EM posterior | Included | Included, weight `1 − posterior` |

**Rationale**: Each row is a spec edge case, and the shared principle is that exclusion from the *estimate* must never become exclusion from the *exposure* — dropping a frozen-pay employee from the denominator would inflate the promotion rate, which is the same class of error as the original bug.

Pay freezes deserve specific note: they create a point mass at exactly zero growth that no Gaussian describes, and left in the sample they drag the ordinary component's variance up and can destabilize the fit. Fitting the mixture only on the strictly-positive continuous part and assigning weight 0 elsewhere is both numerically sound and substantively right — a promotion in this model always comes with a raise. A frozen year is genuine ordinary-raise behavior (merit of zero), so it stays in the merit pool at full weight; excluding it would bias merit upward.

Top-level employees cannot be promoted (`synthetic_census.py:143` encodes the same rule, and `promotion_level_factor` already dampens toward zero by level). Forcing weight 0 rather than letting EM assign them mass prevents the top level's ordinary raises from being read as promotions to a level that does not exist.

---

## R-6: numpy vs. pure Python

**Decision**: numpy.

**Rationale**: Already a declared dependency (`pyproject.toml:20`, alongside scipy and pandas), so this adds nothing to the install. A pure-Python EM over a 100K-row transition table at 200 iterations would be roughly 10⁸ interpreted float operations — tens of seconds, against a vectorized runtime well under one second. Constitution VI sets the 100K-record bar explicitly.

scipy is available but not needed: the two-component Gaussian E and M steps are a handful of vectorized expressions, and pulling in `sklearn`-style machinery would obscure the determinism guarantees this design depends on.

---

## R-7: The grading harness is currently degenerate

**Finding**: `tests/fixtures/synthetic_census.py:144` reads:

```python
raise_pct = truth.promotion_raise if promoted else truth.merit + truth.cola
```

Every non-promoted survivor receives *exactly* 0.055 and every promoted survivor *exactly* 0.18. The observed growth distribution is two point masses with **zero variance**.

**Why this matters**: it invalidates the harness for grading this feature in both directions.

- The mixture would separate two point masses perfectly and trivially. A passing `test_promotion_rate_recovered` would demonstrate nothing about client data, where raises are dispersed.
- Zero within-component variance is a numerical failure mode: `sigma → 0` drives the Gaussian density to infinity and the standardized separation to a division by zero. The estimator would need degenerate-case handling that exists solely to serve an unrealistic fixture.
- The negative case (US2 — genuinely inseparable populations) is *unconstructible* without dispersion. There is no way to make two point masses overlap.

**Decision**: Add dispersion to `TruthRates` before any estimator work — `merit_sigma` (default ≈ 0.015) and `promotion_sigma` (default ≈ 0.04), applied as deterministic lognormal jitter from the existing seeded `rng`. Defaults chosen so the components remain separable (the positive case still passes) while the test stops being trivial. The US2 negative case is then a second `TruthRates` instance with a small promotion raise and wide merit sigma, constructed so the components genuinely overlap.

This is a prerequisite, not a nice-to-have: it is the first task in the Phase 2 plan, ahead of the estimator itself.

**Secondary note**: dispersion also makes the *existing* `test_merit_recovered_per_level` a real test. It currently passes against a distribution where the median is the only value present.

---

## Resolved unknowns from Technical Context

No `NEEDS CLARIFICATION` markers remain. All five spec clarifications (session 2026-08-01) were resolved before planning, and the four research questions they left open — estimator, separation criterion, determinism strategy, degenerate-input handling — are decided above.

One item is deliberately deferred to implementation rather than research: the **numeric tolerances** in SC-001/SC-002 are borrowed from the existing termination assertion and remain unmeasured. Phase 2 group 2 produces real recovery numbers early, before any surface work is built on top, so a revision lands with evidence rather than by negotiation.
