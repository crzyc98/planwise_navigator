# Phase 1 Data Model: Seed Ensembles

**Feature**: 133-seed-ensemble-bands | **Date**: 2026-08-03

Two layers: in-process Pydantic models (planning, results, reporting) and
ensemble-local DuckDB evidence, aggregate, attribution, and provenance tables.

---

## Persisted

### `fct_metric_distributions` (ensemble database)

The aggregate. One row per (scenario, metric, year). Written by `planalign_ensemble.aggregate`, never by dbt (it spans sibling databases — research.md D4).

| Column | Type | Null | Notes |
|---|---|---|---|
| `ensemble_id` | VARCHAR | no | Groups all rows of one ensemble |
| `scenario_id` | VARCHAR | no | |
| `metric` | VARCHAR | no | Canonical metric name (see below) |
| `simulation_year` | INTEGER | no | |
| `p10`,`p25`,`p50`,`p75`,`p90` | DOUBLE | **yes** | NULL ⇔ insufficient sample (FR-013). Never 0-as-missing (FR-013a) |
| `mean` | DOUBLE | yes | NULL under the same condition |
| `stddev` | DOUBLE | yes | NULL under the same condition; sample (n−1) convention |
| `n_seeds` | INTEGER | no | Successful seeds contributing (FR-026) |
| `n_seeds_requested` | INTEGER | no | Requested, so failures are visible in the row itself |
| `is_sufficient` | BOOLEAN | no | FALSE ⇒ percentile columns are NULL (FR-013) |
| `percentile_method` | VARCHAR | no | `'linear'` (FR-010) — recorded so a future change is detectable |

**Grain**: `(ensemble_id, scenario_id, metric, simulation_year)` — unique.

**Invariants**
1. `is_sufficient = FALSE` ⟺ every percentile/mean/stddev column is NULL.
2. `n_seeds ≤ n_seeds_requested`.
3. `is_sufficient = TRUE` ⟹ `n_seeds ≥` configured minimum.
4. Rows are bit-identical across repeat ensembles at the same seed list and configuration (SC-002).

**Canonical metrics** (FR-009): `active_headcount`, `total_compensation`, `employer_match_cost`, `total_employer_plan_cost`, `participation_rate`, `avg_deferral_rate`.

`total_employer_plan_cost` = `SUM(total_employer_contributions)` (match + core), per FR-009a — reusing the existing snapshot column rather than defining new arithmetic.

---

### `fct_metric_seed_values` (ensemble database)

Per-seed evidence. Retained so percentiles can be independently recomputed (SC-003) and so an insufficient sample still yields usable output (FR-013).

| Column | Type | Notes |
|---|---|---|
| `ensemble_id` | VARCHAR | |
| `scenario_id` | VARCHAR | |
| `metric` | VARCHAR | |
| `simulation_year` | INTEGER | |
| `seed` | BIGINT | |
| `value` | DOUBLE | NULL ⇒ metric absent from that run (FR-016) |

**Grain**: `(ensemble_id, scenario_id, metric, simulation_year, seed)` — unique.

---

### `fct_variance_attribution` (ensemble database)

Optional OFAT attribution evidence. It is written only for an ensemble that
requested `--attribution`, and never alters a per-seed simulation database.

| Column | Type | Notes |
|---|---|---|
| `ensemble_id` | VARCHAR | Groups the comparison with its headline aggregate |
| `scenario_id` | VARCHAR | |
| `metric` | VARCHAR | Canonical metric name |
| `simulation_year` | INTEGER | |
| `subsystem` | VARCHAR | `termination`, `hiring`, `promotion`, `enrollment`, or `merit` |
| `variance_share` | DOUBLE | `1 - frozen_variance / baseline_variance`; NULL for structural absence or a zero variance denominator |
| `baseline_variance` | DOUBLE | Sample variance over the paired baseline seeds |
| `frozen_variance` | DOUBLE | Sample variance over the paired frozen seeds |
| `n_seeds` | INTEGER | Number of paired values used for this metric/year |
| `baselines_reused` | INTEGER | Headline worlds whose seed and fingerprint matched |
| `baselines_executed` | INTEGER | Fresh baseline worlds required after the reuse guard |
| `stochastic_status` | VARCHAR | `stochastic` or `not_stochastic`; the latter has NULL share |

**Grain**: `(ensemble_id, scenario_id, metric, simulation_year, subsystem)` — unique.

**Invariants**

1. No attribution row is written for a metric/year below `min_seeds`.
2. `not_stochastic` rows have `variance_share = NULL`, never `0.0`.
3. Frozen and baseline values are paired by the same seed before sample variance is calculated.

---

### `run_metadata` ensemble columns (additive)

Extended through the existing `_evolve_provenance_schema` additive pattern (research.md D7) — no migration, no rewrite.

| Column | Type | Notes |
|---|---|---|
| `ensemble_id` | VARCHAR | NULL for ordinary single runs |
| `ensemble_seed_list` | VARCHAR | Canonical JSON array, ordered |
| `ensemble_seed_count` | INTEGER | |
| `ensemble_role` | VARCHAR | `headline` \| `attribution_frozen` \| `attribution_baseline` |
| `ensemble_frozen_subsystem` | VARCHAR | Set only for `attribution_frozen` |
| `ensemble_member_paths` | VARCHAR | Canonical JSON of per-seed database paths (FR-023) |

`config_fingerprint` is reused as-is for the FR-019b reuse guard: `compute_config_fingerprint` already strips `random_seed`, so fingerprint equality means "same configuration, any seed" — exactly the required predicate.

---

## In-process (Pydantic v2)

### `EnsembleSpec`
Validated request. `scenario_id`, `seed_count`, optional explicit `seed_list`, `base_seed`, `start_year`/`end_year`, `thresholds`, `min_seeds` (default 10), `attribution` flag, `attribution_seed_count`, `discard_seed_dbs`.

**Validation**: `seed_count ≥ 1`; `seed_list` entries unique — **duplicates rejected with the repeated seeds named**, never silently de-duplicated (spec Edge Cases); `attribution_seed_count ≤ seed_count`; `min_seeds ≥ 1`.

### `SeedPlan`
The resolved, frozen plan produced *before any worker starts* (FR-004): ordered `seeds`, per-seed `db_path`, `ensemble_db_path`, `config_fingerprint`, `total_run_count` (disclosed per FR-021), `estimated_disk_mib`.

Seeds are derived deterministically from `base_seed` and `seed_count` when no explicit list is given (FR-005), so a given pair always yields the same list.

### `Threshold`
`metric`, `value`, optional `label`. Resolves to `evaluable` / `not_evaluable` with a reason naming the missing metric (FR-016).

### `SeedRunOutcome`
Per-seed result: `seed`, `db_path`, `status`, `error`, `duration_seconds`. Failures carry their reason through to the report (FR-013, SC-009).

### `MetricDistribution`
In-process mirror of the persisted row, including `is_sufficient`. Constructed only through the aggregation path so the sufficiency invariant cannot be bypassed.

### `RiskStatement`
`metric`, `threshold_value`, `simulation_year`, `exceedance_probability`, `n_seeds`, `is_evaluable`.

Excludes insufficient-sample metrics (FR-013c).

### `AttributionShare`
`metric`, `simulation_year`, `subsystem`, `variance_share`, `baseline_variance`, `frozen_variance`, `n_seeds`, `baselines_reused`, `baselines_executed` (FR-019c), and `stochastic_status`.

`stochastic_status` ∈ `{stochastic, not_stochastic}`. Enrollment and merit report `not_stochastic` with `variance_share = None` — **never 0.0** (research.md D1). This is the field that keeps a structural absence from reading as a measured finding.

### `Subsystem`
Enumeration of freezable subsystems with their dbt variable names and whether they are seed-variant today:

| Subsystem | dbt var | Seed-variant | v1 attributable |
|---|---|---|---|
| `termination` | `random_seed_termination` | yes | **yes** |
| `hiring` | `random_seed_hiring` | yes | **yes** |
| `promotion` | `random_seed_promotion` | yes | **yes** |
| `enrollment` | — | **no** (10 unseeded sites) | no — reported `not_stochastic` |
| `merit` | — | **no** (no draws at all) | no — reported `not_stochastic` |

---

## Relationships

```
EnsembleSpec ──plan──> SeedPlan ──execute──> SeedRunOutcome (N)
                                                   │
                                          extract  ▼
                                    fct_metric_seed_values
                                                   │
                                        aggregate  ▼
                                    fct_metric_distributions
                                              │        │
                                       risk   ▼        ▼  attribution
                                     RiskStatement   AttributionShare
```

Attribution additionally consumes frozen-run seed values, paired seed-for-seed against baseline values from the same seed (FR-019), with baseline runs reused from the headline ensemble when seed **and** `config_fingerprint` both match (FR-019a/b).

---

## State transitions

A distribution row is written exactly once and never updated — consistent with Principle I. An ensemble moves `planned → running → aggregated`, or `planned → running → failed`. An interrupted ensemble writes no aggregate at all (SC-010): the aggregate appears only after every seed has terminally resolved, so a partial aggregate is unrepresentable rather than merely discouraged.
