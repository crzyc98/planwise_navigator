# Phase 1 Data Model — Promotion Fit Bias

**Feature**: 130-promotion-fit-bias | **Date**: 2026-08-01

No database schema changes. The fitter runs in an in-memory DuckDB and emits a parameter-pack directory; these are in-process types and one added transition column.

---

## New types (`planalign_fit/models.py`)

### `PromotionBasis` (enum)

The three states of FR-005. One value, threaded through `FitResult` → report → manifest → `param_pack` provenance.

| Value | Meaning |
|---|---|
| `measured` | Job-level coverage cleared the threshold; promotions read directly from level moves. |
| `estimated` | Coverage below threshold or column absent; promotion rate estimated from the raise distribution. |
| `not_fitted` | Estimation attempted but separating levels covered under the exposure gate. Configured default retained throughout. |

### `LevelSeparation` (frozen dataclass)

One job level's verdict on the estimated path. Populates the report's per-level table (FR-004b) and drives which levels contribute fitted rates.

| Field | Type | Notes |
|---|---|---|
| `level_id` | `int` | |
| `separated` | `bool` | Both R-3 conditions met |
| `exposure` | `float` | Continued-employee transitions at this level |
| `estimated_rate` | `Optional[float]` | Mixing weight of the promotion component; `None` when not separated |
| `ordinary_location` | `Optional[float]` | Fitted ordinary-component mean, back-transformed out of log space |
| `promotion_location` | `Optional[float]` | Fitted promotion-component mean, back-transformed |
| `standardized_distance` | `Optional[float]` | `abs(mu2 - mu1) / sigma_pooled`; the R-3 condition-2 statistic |
| `bic_improvement` | `Optional[float]` | `BIC(1 component) - BIC(2 components)`; positive means two won |
| `converged` | `bool` | EM reached tolerance inside the iteration cap |
| `reason` | `str` | Plain-language explanation when `separated` is `False` — feeds FR-004b and FR-007 |

**Validation**: `exposure >= 0`. When `separated` is `True`, `estimated_rate` is in `[0, 1]` and the three diagnostic fields are non-`None`.

### `PromotionClassification` (frozen dataclass)

The run-level record. One instance per fit, carried on `FitResult`.

| Field | Type | Notes |
|---|---|---|
| `basis` | `PromotionBasis` | |
| `level_coverage` | `float` | Share of experienced exposure with a job level at both ends (FR-001a) |
| `level_coverage_threshold` | `float` | Threshold in force, default or analyst-supplied |
| `separated_exposure_share` | `Optional[float]` | Share of experienced exposure held by separating levels (FR-004a); `None` on the `measured` path |
| `exposure_gate` | `float` | Gate in force, default 0.5 |
| `levels` | `list[LevelSeparation]` | Empty on the `measured` path |
| `reason` | `str` | Why this basis was selected; rendered verbatim in the report |

**State transitions** — the routing decision, evaluated once per fit:

```text
                     level_coverage >= threshold ?
                              │
              ┌───────── yes ─┴─ no ──────────┐
              ▼                               ▼
       basis = measured              run per-level mixture
   (weights = observed flag)                  │
                              separated_exposure_share >= gate ?
                                       │
                        ┌───── yes ────┴──── no ─────┐
                        ▼                            ▼
                 basis = estimated           basis = not_fitted
        (separating levels fitted,        (all levels keep default;
         others keep default)              promotion joins unfittable)
```

The transition is one-way and computed before any estimator runs; nothing downstream can change the basis.

---

## Changed types

### `FitResult` (`models.py:120`)

Add `promotion_classification: Optional[PromotionClassification] = None`.

`promotion: Optional[HazardFit]` keeps its type but gains a meaning: `None` now signals `not_fitted`, where previously it was unreachable. `all_fitted()` already guards `if hazard is not None`, so the not-fitted path needs no change there.

### `HazardFit` (`models.py:75`)

No field changes. `total_events: float` is already a float and now carries an **expected** count (a sum of fractional weights) on the estimated path rather than a whole-number tally. `observed_overall_rate` is unchanged and remains correct.

Report formatting is the one consequence: `report.py:117` renders events as `{:,.0f}`, which would print 412.7 expected promotions as "413". The promotion section needs one decimal place on the estimated path.

### `Priors` / `HazardPriors` (`priors.py`)

Add a read of `promotion_compensation.base_increase_pct` (`config/simulation_config.yaml:37`, default 0.20) for EM initialization (R-4). Reached through the existing `Priors.config_value` accessor — no new seed file, no new loader.

### `FitOptions` (`runner.py:30`)

Two fields, per FR-015:

| Field | Type | Default | Constraint |
|---|---|---|---|
| `level_coverage_threshold` | `float` | `0.95` | `0 < v <= 1` |
| `separation_exposure_gate` | `float` | `0.50` | `0 < v <= 1` |

The R-3 separation constants are deliberately **not** here — they are module-level constants in `promotion.py`, unreachable from the CLI (FR-016).

### `TransitionObservability` (`transitions.py:45`)

Replace `has_explicit_level: bool` with `level_coverage: float`.

This is the bug fix. The current boolean is `"level_id" in common` (`transitions.py:202`) — a whole-column presence check — while `_banded_projection` (`transitions.py:141`) coalesces to band derivation *per row*. A census with one populated `level_id` therefore reports itself as directly measured and silently band-derives everyone else. Coverage is measured over transitions requiring a level at **both** ends, since a promotion is only directly observable across a pair.

---

## New transition column

`promotion_weight DOUBLE` on the transition table (`transitions.py:_pair_transition_sql`).

| Path | Value |
|---|---|
| `measured` | `CASE WHEN promoted THEN 1.0 ELSE 0.0 END` |
| `estimated` | EM posterior, joined in from a `promotion_weights` staging table keyed by `employee_id, from_year` |
| Forced-zero cases (R-5) | `0.0` |

The existing `promoted BOOLEAN` column stays — it is the authoritative-path input and the source of the measured weights.

**Invariant**: `0.0 <= promotion_weight <= 1.0` for every row, on every path. This is the single assertion that keeps both consumers honest, and it is worth a test of its own.

---

## Consumers of `promotion_weight`

Both existing call sites become weighted versions of themselves. Neither changes shape.

### Promotion hazard (`hazards.load_cells`, `hazards.py:155`)

```sql
-- before
SUM(CASE WHEN promoted THEN 1 ELSE 0 END) AS events
-- after
SUM(promotion_weight) AS events
```

`CellObservation.events` and `ipf.FactorCell.events` are already `float`, so the IPF solver accepts fractional events with **no change at all**. On the measured path the weights are 0/1 and the sum is bit-for-bit today's count.

### Merit (`compensation.observed_merit_by_level`, `compensation.py:38`)

```sql
-- before
MEDIAN(compensation_growth) ... WHERE continued AND NOT promoted
-- after
weighted median of compensation_growth with weight (1 - promotion_weight), WHERE continued
```

DuckDB has no built-in weighted median, so this is a small SQL construction (cumulative weight over an ordered scan, take the 50% crossing) or a numpy computation over the fetched per-level arrays. The numpy route is preferred: it keeps the interpolation rule explicit and testable, and the per-level arrays are small.

Exposure reported alongside becomes the **effective** exposure `SUM(1 - promotion_weight)` rather than a row count, so credibility shrinkage (`shrink_ratio`, `smoothing.py:100`) sees the evidence actually behind the median.

**Clean-path parity** (SC-005, US3 scenario 3): with 0/1 weights the weighted median over all continued employees is identical to the unweighted median over non-promoted employees, and effective exposure equals the old row count. Today's behavior is recovered exactly, not approximately — this is the property that makes FR-008a's "one definition, not a per-path variant" true rather than aspirational.

---

## Pure-numeric types (`planalign_fit/mixture.py`)

Domain-free, mirroring `ipf.py`'s role.

### `MixtureComponent` (frozen dataclass)
`mean: float`, `sigma: float`, `weight: float`

### `MixtureFit` (frozen dataclass)
`ordinary: MixtureComponent`, `promotion: MixtureComponent`, `responsibilities: np.ndarray`, `log_likelihood: float`, `iterations: int`, `converged: bool`, `bic: float`, `single_component_bic: float`

**Invariants**: `ordinary.weight + promotion.weight == 1.0` (within tolerance); `responsibilities` has the same length as the input and every element is in `[0, 1]`; `sigma > 0` for both components (a floor is applied to prevent collapse).

Component identity is fixed by initialization (R-4), so `promotion` is always the higher-location component by construction and no relabeling step exists.

---

## Provenance additions

Detailed in [contracts/pack-provenance.md](./contracts/pack-provenance.md). In summary:

- `PackManifest` gains `promotion_basis: str` and `thresholds: dict[str, float]` (non-default values only, per FR-017).
- `apply.provenance_block` (`apply.py:69`) gains `promotion_basis`, so a simulation run records whether the promotion hazard it used was fitted or defaulted (FR-010).

Both ride the existing mechanism: `SimulationConfig` retains unknown top-level keys and `to_dbt_vars` ignores them, so the `param_pack` block reaches `run_metadata` **without perturbing the config fingerprint** (`apply.py:70-75`). Provenance, not a result-affecting input — the same property the block was designed around in #458.
