# Phase 1 Data Model: Backtest Scorecard

All entities are Pydantic v2 models in `planalign_backtest/models.py` (Constitution V). The JSON artifact is serialized directly from `Scorecard`, so the documented schema in `contracts/scorecard.schema.json` is generated from these models and cannot drift from the code.

Frozen models throughout — a scorecard is evidence, and evidence should not be mutable after construction.

---

## SnapshotSplit

The fit/holdout partition of a snapshot set. Produced by `planalign_backtest/split.py`.

| Field | Type | Notes |
|---|---|---|
| `fit_years` | `tuple[int, ...]` | Years fed to the fitter. Length ≥ 2. |
| `holdout_years` | `tuple[int, ...]` | Years scored against. Length 1–2. |
| `boundary_year` | `int` | `max(fit_years)`. The census the simulation starts from. |
| `all_years` | `tuple[int, ...]` | Full set, for provenance. |

**Validation rules**

- `len(fit_years) >= 2` — the fitter's own `MIN_SNAPSHOTS` (`planalign_fit/snapshots.py:24`). Violation → rejection naming both counts (FR-004).
- `1 <= len(holdout_years) <= 2` (FR-002). A larger request is rejected, never clamped.
- `fit_years` and `holdout_years` are disjoint and jointly exhaustive of `all_years`.
- `all_years` is consecutive with no gaps — inherited from `_validate_set`; a gap is rejected before splitting.
- `min(holdout_years) == boundary_year + 1` — the holdout immediately follows the fit boundary.

**Derivation**: given `n` snapshots and holdout length `h`, `holdout_years` is the last `h` years and `fit_years` the rest. Feasibility therefore requires `n >= h + 2`, i.e. at least 3 snapshots for the default `h=1`.

---

## BacktestOptions

Everything an analyst can turn without changing what a metric means.

| Field | Type | Default | Notes |
|---|---|---|---|
| `holdout_years` | `int` | `1` | 1 or 2 (FR-002). |
| `seeds` | `tuple[int, ...]` | `(42, 43, 44)` | 1–5 entries, unique (FR-007). Base `42` matches `SimulationConfig.random_seed`. |
| `thresholds` | `MetricThresholds` | see below | FR-016. |
| `output` | `Path \| None` | `None` | Pack destination; defaults to the fitter's convention. |
| `base_config` | `Path \| None` | `None` | Base simulation config; defaults to `config/simulation_config.yaml`. |
| `workdir` | `Path \| None` | `None` | Defaults to `var/backtests/<timestamp>-<pack_id>/`. |
| `fit_options` | `FitOptions` | default | Passed through; `only_years` is set by the runner and may not be supplied by a caller. |
| `force` | `bool` | `False` | Permit overwriting an existing scorecard (FR-029). |

**Validation rules**

- `seeds` non-empty, ≤ 5, no duplicates. Duplicate seeds would produce identical runs and a falsely narrow spread.
- `fit_options.only_years` must be unset on input — the runner owns it (R1). Supplying it is a programming error and raises.

---

## MetricThresholds

Percentage-error boundaries for pass/warn/fail, per metric family.

| Field | Type | Default (warn / fail) | Covers |
|---|---|---|---|
| `headcount` | `Threshold` | 2% / 4% | total and all headcount breakdowns |
| `compensation` | `Threshold` | 3% / 6% | total and average compensation |
| `flows` | `Threshold` | 10% / 20% | termination, hire, promotion counts |
| `plan` | `Threshold` | 5% / 10% | participation rate, average deferral, match cost |

`Threshold` is `{warn: float, fail: float}` with `0 < warn < fail`. Defaults for `headcount` and `compensation` are fixed by FR-016; the others are set here and printed on every scorecard (FR-017).

Flow thresholds are deliberately looser: counts of discrete events in a single year carry far more sampling noise than a headcount, and a tight threshold there would produce red cells that mean nothing. This choice is stated on the scorecard rather than hidden.

---

## SeedRun

One completed simulation for one seed.

| Field | Type | Notes |
|---|---|---|
| `seed` | `int` | |
| `database` | `Path` | Isolated per-seed DB (FR-006). |
| `config_fingerprint` | `str` | From `run_metadata`; differs per seed by construction (R7). |
| `years_simulated` | `tuple[int, ...]` | Must equal `split.holdout_years`. |

A failed run produces no `SeedRun`; the whole backtest fails naming seed and year (FR-032).

---

## MetricValue and MetricComparison

`MetricValue` is one scored quantity for one period:

| Field | Type | Notes |
|---|---|---|
| `metric` | `str` | Stable identifier, e.g. `headcount.total`, `headcount.by_level.3`, `compensation.average`, `flows.terminations`, `plan.participation_rate`. |
| `period` | `int \| "cumulative"` | A held-out year, or the cumulative row (FR-013). |

`MetricComparison` is the scored result:

| Field | Type | Notes |
|---|---|---|
| `metric` | `str` | |
| `period` | `int \| "cumulative"` | |
| `observable` | `bool` | `False` when the census lacks the source column (FR-012). |
| `unobservable_reason` | `str \| None` | Required when `observable` is `False`; reuses `Observability.reasons()` text. |
| `predicted` | `float \| None` | Headline value: per-metric lower median across seeds (R5). `None` iff not observable. |
| `actual` | `float \| None` | From the held-out census. `None` iff not observable. |
| `absolute_error` | `float \| None` | `predicted - actual`. Signed — direction of miss is diagnostic. |
| `percent_error` | `float \| None` | `absolute_error / actual`. `None` when `actual == 0` (FR-018). |
| `threshold` | `Threshold \| None` | The threshold applied. |
| `status` | `"pass" \| "warn" \| "fail" \| "not_observable" \| "undefined"` | `undefined` when percent error is undefined but the metric is observable. |
| `spread` | `SeedSpread \| None` | `None` for single-seed runs (FR-022). |

**Validation rules**

- `observable is False` ⟺ `status == "not_observable"` ⟺ all numeric fields `None`.
- `actual == 0` ⟹ `percent_error is None` and `status == "undefined"`; `absolute_error` is still reported.
- `status` is derived from `percent_error` and `threshold`, never set independently — one function, `scoring.classify`, owns it.

**Cumulative semantics**, fixed here so the two sides cannot disagree:
- Stock metrics (headcount, compensation) — the value at the **final** held-out year, not a sum. Summing headcounts across years is meaningless.
- Flow metrics (terminations, hires, promotions, match cost) — the **sum** across held-out years.
- Rate metrics (participation, average deferral) — the value at the final held-out year.

---

## SeedSpread

Per-metric dispersion across seeds (FR-020).

| Field | Type | Notes |
|---|---|---|
| `seed_count` | `int` | ≥ 2 whenever a spread exists. |
| `minimum` | `float` | |
| `maximum` | `float` | |
| `values` | `tuple[float, ...]` | One per seed, in seed order — reproducibility inspection. |
| `actual_within_spread` | `bool` | Whether `actual` falls in `[minimum, maximum]`. |
| `distance_outside` | `float \| None` | Signed distance beyond the nearer bound; `None` when inside. |

---

## BacktestProvenance

The audit chain (FR-025).

| Field | Type | Notes |
|---|---|---|
| `snapshots` | `tuple[SnapshotRef, ...]` | Every source snapshot: year, filename, `sha256`, row count, and `role` ∈ {`fit`, `holdout`}. |
| `source_digest` | `str` | Over the fitted snapshots only — matches the pack manifest. |
| `pack_id` | `str` | |
| `pack_fingerprint` | `str` | Fingerprint at backtest time; staleness is detected by comparison (FR-026, R8). |
| `promotion_basis` | `str` | Carried from the manifest — whether promotions were fitted or defaulted (#511). |
| `level_basis` | `"census_level_id" \| "compensation_band"` | Which basis produced by-level headcount (R3). |
| `compensation_basis` | `str` | Fixed to the annualized rate (R4); recorded so a reader need not infer it. |
| `backtest_date` | `str` | ISO-8601 UTC. |
| `tool_version` | `str` | From `_version.__version__`. |

---

## Scorecard

The root artifact.

| Field | Type | Notes |
|---|---|---|
| `schema_version` | `str` | Semantic; bumped on incompatible structure change (FR-024). Starts at `1.0.0`. |
| `scorecard_fingerprint` | `str` | SHA-256 over the canonical JSON of every other field. Identifies this scorecard in `run_metadata` (R9). |
| `split` | `SnapshotSplit` | |
| `seeds` | `tuple[int, ...]` | |
| `seed_runs` | `tuple[SeedRun, ...]` | |
| `thresholds` | `MetricThresholds` | Printed on the artifact (FR-017). |
| `overridden_thresholds` | `tuple[str, ...]` | Which families the analyst moved — the dial-turning is visible, as `planalign_fit` does with `_moved_thresholds`. |
| `comparisons` | `tuple[MetricComparison, ...]` | Every metric × period. |
| `verdict` | `"pass" \| "warn" \| "fail"` | Worst status among observable comparisons; `undefined` and `not_observable` do not contribute (FR-019). |
| `verdict_summary` | `str` | E.g. `"14 pass, 2 warn, 1 fail, 3 not observable"`. |
| `provenance` | `BacktestProvenance` | |
| `notes` | `str` | Analyst-supplied. |

**Validation rules**

- `comparisons` covers every metric in the registry for every held-out year plus `cumulative`; no metric is silently absent (SC-003). Unsupported ones appear with `status = "not_observable"`.
- `verdict` is derived, never assigned.
- `scorecard_fingerprint` excludes itself and is computed over canonical JSON — sorted keys, fixed float formatting — so an identical rerun produces an identical fingerprint (SC-005).

**Determinism**: every collection is an ordered tuple with a defined sort (comparisons by metric identifier then period; snapshots by year; seeds as supplied). No `set` or `dict` iteration reaches the artifact.

---

## Metric registry

The fixed metric identifiers, their family (which threshold applies), cumulative rule, and observability source. Defined once in `models.py` and iterated by both the actuals and predicted extractors, so neither can quietly omit a metric.

| Metric id | Family | Cumulative | Requires |
|---|---|---|---|
| `headcount.total` | headcount | final | always |
| `headcount.by_level.<n>` | headcount | final | always |
| `headcount.by_age_band.<band>` | headcount | final | always |
| `headcount.by_tenure_band.<band>` | headcount | final | always |
| `compensation.total` | compensation | final | always |
| `compensation.average` | compensation | final | always |
| `flows.terminations` | flows | sum | always |
| `flows.hires` | flows | sum | always |
| `flows.promotions` | flows | sum | `level_coverage` sufficient, else not observable |
| `plan.participation_rate` | plan | final | enrollment or deferral column |
| `plan.average_deferral_rate` | plan | final | `employee_deferral_rate` |
| `plan.employer_match_cost` | plan | sum | deferral column (match is otherwise unobservable in a census) |

Observability is evaluated **per held-out year**, so a column present in some years and absent in others degrades only the affected years (spec edge case).

---

## Entity relationships

```text
BacktestOptions ──drives──> SnapshotSplit ──feeds──> ParameterPack (planalign_fit)
                                  │                        │
                                  │                        └──> AppliedPack ──> SeedRun (×N, isolated DBs)
                                  │                                                  │
                            holdout years                                       predicted
                                  │                                                  │
                                  └──> actual metrics ────────┬─────────────────────┘
                                                              │
                                                        MetricComparison (×metrics×periods)
                                                              │
                                                          Scorecard ──> <pack>/backtest/
                                                              │
                                                              └──> run_metadata.backtest_score_ref
```
