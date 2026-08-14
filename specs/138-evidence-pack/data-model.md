# Data Model: Evidence Packs — Cited Driver Decomposition

This feature adds no persisted entity or public mart. The entities below are
immutable Pydantic response/domain objects assembled from one read-only result
database and discarded after response/rendering.

## Canonical types

### `MetricId`

Closed literal set inherited from `planalign_ensemble.models.CANONICAL_METRICS`:

```text
active_headcount
total_compensation
employer_match_cost
total_employer_plan_cost
participation_rate
avg_deferral_rate
```

No API or CLI alias is accepted as a second identifier. User-facing labels may
say “Average deferral rate,” but the stable ID remains `avg_deferral_rate`.

### `FigureStatus`

```text
defined | undefined | suppressed
```

- `defined`: `value` is a canonical decimal string and `reason` is null.
- `undefined`: `value` is null and `reason` explains the mathematical or
  source-data condition.
- `suppressed`: the underlying absolute figure may remain available elsewhere,
  but this presentation (normally share of change) has no value because it
  would be unstable or misleading.

## Aggregate response entities

### `Citation`

The exact reproducibility pointer for one figure.

| Field | Type | Required | Rule |
|---|---|---:|---|
| `result_store` | string | yes | Run-relative locator ending in `simulation.duckdb`; never an absolute host path |
| `query_id` | string | yes | `Q1` in v1 |
| `query` | string | yes | Exact standalone read-only aggregate SQL used for the pack |
| `result_column` | string | yes | Unique allowlisted output column that reproduces this figure |

Validation rules:

- `query` contains exactly one aggregate `SELECT` statement built from the
  fixed metric registry. It contains no `ATTACH`, `COPY`, `CREATE`, `INSERT`,
  `UPDATE`, `DELETE`, `DROP`, `ALTER`, `PRAGMA`, sampling, or external path.
- Requested years appear as validated integer literals so the exported query
  is directly executable without bind parameters.
- Result columns contain no employee identifier or employee-level value.

### `EvidenceFigure`

One displayed/cited scalar.

| Field | Type | Required | Rule |
|---|---|---:|---|
| `value` | decimal string or null | yes | Fixed-scale finite canonical representation; no JSON float |
| `unit` | `count` \| `currency` \| `rate` \| `percent_of_change` | yes | Determines display only |
| `status` | `FigureStatus` | yes | Controls value/reason invariant |
| `reason` | string or null | yes | Required unless status is `defined` |
| `citation` | `Citation` | yes | Re-executes to this scalar/result column |

Canonical numeric rules:

- Count strings have scale 0.
- Currency and rate calculations retain up to 12 decimal places, with trailing
  zero normalization defined once in the renderer/model helper.
- Negative zero normalizes to `0`.
- NaN and infinity are invalid.

### `PopulationEvidence`

An aggregate explanation of the people summarized by one driver.

| Field | Type | Required | Description |
|---|---|---:|---|
| `label` | string | yes | Stable plain-language cohort description |
| `count` | `EvidenceFigure` | yes | Aggregate count cited to `Q1.<population_column>` |
| `base_count` | `EvidenceFigure` or null | no | Used when a transition needs both endpoints |
| `target_count` | `EvidenceFigure` or null | no | Used when a transition needs both endpoints |
| `changed_count` | `EvidenceFigure` or null | no | Retained rows whose status/value changed |

No employee identifiers, examples, minimum/maximum employee values, or small-
cell row excerpts are permitted.

### `DriverContribution`

One fixed named component of a metric’s movement.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | metric-specific literal | yes | Stable machine identifier |
| `label` | string | yes | User-facing name |
| `description` | string | yes | Meaning and boundaries of the driver |
| `contribution` | `EvidenceFigure` | yes | Signed absolute contribution |
| `share_of_change` | `EvidenceFigure` | yes | Signed percent; may be suppressed |
| `population` | `PopulationEvidence` | yes | Aggregate cohort/count behind the line |
| `base_rate` | `EvidenceFigure` or null | no | Retained effective payout rate at the base endpoint |
| `target_rate` | `EvidenceFigure` or null | no | Retained effective payout rate at the target endpoint |

Drivers are emitted in registry order, never sorted by magnitude. This makes
repeated packs and exports byte-stable.

### `Residual`

Always-present unexplained portion. Structurally separate from named drivers so
it cannot be silently reclassified.

| Field | Type | Required | Description |
|---|---|---:|---|
| `contribution` | `EvidenceFigure` | yes | `total_change - SUM(defined named contributions)` at canonical scale |
| `share_of_change` | `EvidenceFigure` | yes | Same suppression rule as named shares |
| `material` | boolean | yes | Magnitude exceeds the deterministic materiality threshold |
| `largest_contribution` | boolean | yes | Nonzero magnitude is at least every defined named contribution |

A zero residual is emitted as a defined `0`, never omitted. Undefined named
drivers are excluded from the sum; their unattributed movement therefore stays
visible in residual.

### `MetricChange`

| Field | Type | Required | Description |
|---|---|---:|---|
| `metric` | `MetricId` | yes | Canonical identifier |
| `label` | string | yes | User-facing label |
| `base_year` | integer | yes | Requested earlier endpoint |
| `target_year` | integer | yes | Requested later endpoint |
| `base_value` | `EvidenceFigure` | yes | Canonical headline value in base year |
| `target_value` | `EvidenceFigure` | yes | Canonical headline value in target year |
| `total_change` | `EvidenceFigure` | yes | Target minus base |
| `base_population` | `EvidenceFigure` | yes | Cited canonical denominator/population at the base endpoint |
| `target_population` | `EvidenceFigure` | yes | Cited canonical denominator/population at the target endpoint |
| `shares_suppressed_reason` | string or null | yes | Common reason applied to every share |

Validation: `base_year < target_year`; both years must exist in the selected
result. Non-adjacent years are valid.

### `PackWarning`

| Field | Type | Required | Description |
|---|---|---:|---|
| `code` | warning literal | yes | Stable programmatic condition |
| `severity` | `info` \| `caution` \| `critical` | yes | Studio presentation |
| `message` | string | yes | Self-contained explanation and consequence |

Warning codes in v1:

```text
run_in_progress
legacy_result
current_config_mismatch
current_seed_mismatch
mixed_generation
incomplete_build
incomplete_provenance
integrity_mismatch
material_residual
residual_dominates
shares_suppressed
```

Warnings are sorted by fixed severity/code order, not discovery order.

### `PackProvenance`

| Field | Type | Required | Description |
|---|---|---:|---|
| `workspace_id` | string or null | no | Present for managed Studio result |
| `scenario_id` | string | yes | Scenario identity |
| `scenario_name` | string or null | no | Human label; not a substitute for ID |
| `run_id` | UUID string or `legacy` | yes | Exact result identity |
| `run_timestamp` | UTC datetime or null | yes | Null produces an incomplete-provenance warning |
| `random_seed` | integer or null | yes | Null produces an incomplete-provenance warning |
| `config_fingerprint` | 64-char SHA-256 or null | yes | Full fingerprint, not display-truncated |
| `result_store` | string | yes | Same run-relative locator used by citations |
| `verification_disposition` | `fully_verified` \| `incomplete` \| `unverifiable` | yes | Reused archive report disposition or legacy fallback |

The in-database `run_metadata` row must match the bound managed `run_id`. The
service must not select a different row merely because it is latest by time.

### `EvidencePack`

The complete answer to one request.

| Field | Type | Required | Description |
|---|---|---:|---|
| `schema_version` | literal `1.0` | yes | Response/export compatibility |
| `generated_at` | absent | — | Deliberately omitted to keep identical invocations byte-stable |
| `provenance` | `PackProvenance` | yes | Bound selected result |
| `change` | `MetricChange` | yes | Endpoints and total movement |
| `drivers` | ordered list[`DriverContribution`] | yes | Registry-defined lines |
| `residual` | `Residual` | yes | Always present |
| `warnings` | ordered list[`PackWarning`] | yes | May be empty |
| `executive_summary` | ordered list[string] | yes | Deterministic business interpretation derived from cited figures |
| `population_note` | string | yes | Defines snapshot/entering/leaving treatment |

Cross-entity invariants:

1. Every figure has a citation to the same `result_store` and query text.
2. `total_change = target_value - base_value` at canonical scale.
3. `total_change = SUM(defined driver contributions) + residual` exactly.
4. When shares are defined, each is computed directly as
   `100 * contribution / total_change`; their sum is within one canonical rate
   quantum of `100`. No share is adjusted merely to balance rounding.
5. Driver IDs/order exactly match the registry for the selected metric.
6. Serialization contains no employee-level field or absolute filesystem path.

### `EvidencePackEnvelope`

API response containing:

| Field | Type | Required | Description |
|---|---|---:|---|
| `pack` | `EvidencePack` | yes | Structured Studio data |
| `text_export` | string | yes | Canonical Markdown rendered from exactly `pack` |
| `filename` | string | yes | Safe deterministic `.md` filename |

The CLI calls the same renderer and emits `text_export` byte-for-byte.

## Fixed decomposition identities

Let base and target years be 0 and 1. `S` is the intersection of metric-
denominator rows by `employee_id`, `E` target-only rows, and `L` base-only rows.
For all-row metrics, a retained employee who becomes terminated remains in `S`;
“entered/left” describes the canonical snapshot population, not employment
status.

### Active headcount

With active indicator `a`:

```text
new_active_records        = SUM_E(a1)
removed_active_records    = -SUM_L(a0)
retained_became_active    = COUNT_S(a0=0 AND a1=1)
retained_ceased_active    = -COUNT_S(a0=1 AND a1=0)
```

### Total compensation

With prorated compensation `c`:

```text
entered_population_compensation     = SUM_E(c1)
left_population_compensation        = -SUM_L(c0)
retained_compensation_and_proration = SUM_S(c1-c0)
```

The retained label deliberately includes compensation, promotion, proration,
and employment-timing effects that cannot be separated from the canonical
snapshot field.

### Employer match / total employer plan cost

Use `x = employer_match_amount` or `total_employer_contributions`. For retained
rows, `C0/C1 = SUM(c0/c1)`, `X0/X1 = SUM(x0/x1)`, and `r0/r1 = X0/C0, X1/C1`:

```text
entered_population_cost        = SUM_E(x1)
left_population_cost           = -SUM_L(x0)
retained_compensation_exposure = (C1-C0) * (r0+r1) / 2
retained_effective_payout_rate = (r1-r0) * (C0+C1) / 2
```

The two retained terms sum exactly to `X1-X0`. If either retained compensation
denominator is zero, both retained terms are undefined and the retained
movement remains in residual. A zero payout numerator with positive
compensation is defined at rate zero.

### Participation / average deferral rate

Let numerator `T` be participating count `Q` or deferral sum `D`, denominator
`N`, `w = (1/N0 + 1/N1)/2`, and
`z = (T0+T1) * (1/N1 - 1/N0)/2`:

```text
retained_behavior        = w * SUM_S(value1-value0)
entered_population       = w * SUM_E(value1)
left_population          = -w * SUM_L(value0)
population_reweighting   = z
```

These four terms equal `T1/N1 - T0/N0`. Participation uses binary value `q`;
average deferral uses `d` and excludes null rates from each endpoint set to
preserve SQL `AVG` semantics. If either endpoint `N` is zero, the decomposition
is unavailable rather than reported as zero.

## State flow

```text
Requested
  -> Resolved to concrete run/database
  -> Schema and year support validated
  -> Aggregate query executed read-only
  -> Typed pack reconciled and warnings attached
  -> Structured response + canonical text rendered
```

There is no persisted pack state, cache, result-table write, or archive update.
Any failure leaves the source result unchanged.
