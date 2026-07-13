# Data Model: Studio Two-Scenario Diff View

**Feature**: 110-scenario-diff-view | **Date**: 2026-07-12

This feature adds response models only. It creates no tables and persists no state.

## Entity: Scenario Pair

An ordered pair of distinct completed scenarios in one workspace.

| Field | Type | Rules |
|---|---|---|
| `scenario_a` | string | Required; exists in workspace; completed; baseline for deltas |
| `scenario_b` | string | Required; exists in workspace; completed; differs from `scenario_a` |
| `scenario_names` | map<string, string> | Contains display names for exactly A and B |

Relationships: owns two effective configurations and two provenance values; selects corresponding values from annual metric comparisons.

## Entity: Workforce Metrics

Existing annual workforce value extended additively.

| Field | Type | Rules |
|---|---|---|
| `headcount` | integer | Distinct employees in the year |
| `active` | integer | Distinct active employees |
| `terminated` | integer | Distinct terminated employees |
| `new_hires` | integer | Hire events in the year |
| `growth_pct` | number | Change from prior annual headcount |
| `avg_compensation` | number | Average prorated annual compensation for active employees; `0.0` when none |

In a `deltas` map, every field is scenario value minus baseline value. `avg_compensation` therefore permits negative values.

## Entity: Effective Configuration

An in-memory mapping produced by the established workspace base-plus-scenario-override resolver. It is not returned wholesale and is never persisted by this feature.

Validation rules:

- Both configurations must resolve for scenarios that passed router validation.
- Atomic/default/reconciliation behavior comes only from the existing resolver.
- Cosmetic leaves are filtered before diff/count operations.

## Entity: Configuration Delta

One emitted difference between effective configurations.

| Field | Type | Rules |
|---|---|---|
| `path` | string | Required stable dotted path; unique within response |
| `a` | JSON value or null | A value; null may also accompany `only_b`, whose status disambiguates absence |
| `b` | JSON value or null | B value; null may also accompany `only_a` |
| `status` | enum | `changed`, `only_a`, or `only_b` |

Ordering is lexical by `path`. Mapping children recurse; sequences are atomic JSON values.

## Entity: Scenario Provenance

Read-only interpretation of one scenario database's latest run metadata and, when available, the immediately preceding row.

| Field | Type | Rules |
|---|---|---|
| `available` | boolean | False when legacy/missing/unreadable metadata prevents provenance display |
| `config_fingerprint` | string or null | First 12 characters of latest recorded fingerprint |
| `random_seed` | integer or null | Latest recorded seed |
| `run_timestamp` | ISO-8601 datetime or null | Latest run start timestamp |
| `drift_warning` | boolean | True when displayed results may not match current config or may be mixed-generation |
| `drift_reasons` | array<enum> | Zero or more: `current_config_mismatch`, `current_seed_mismatch`, `mixed_generation` |

`available=false` is not itself drift; the UI reports provenance as unavailable. Errors do not escape the service.

## Entity: Configuration Diff Response

| Field | Type | Rules |
|---|---|---|
| `scenario_a` | string | Echoed validated A ID |
| `scenario_b` | string | Echoed validated B ID |
| `scenario_names` | map<string, string> | Exactly A and B |
| `differences` | array<Configuration Delta> | Sorted; may be empty |
| `unchanged_count` | integer | Count of equal, non-cosmetic leaves; >= 0 |
| `provenance` | map<string, Scenario Provenance> | Exactly A and B |
| `seeds_match` | boolean or null | Null if either latest seed is unavailable |
| `drift_warning` | boolean | OR of per-scenario drift warnings |

## Relationships to Existing Comparison Response

```text
Scenario Pair
├── ComparisonResponse
│   ├── workforce_comparison[year].values[A|B]
│   ├── workforce_comparison[year].deltas[B]
│   └── dc_plan_comparison[year].values/deltas[A|B]
└── ConfigDiffResponse
    ├── differences[]
    └── provenance[A|B]
```

The browser joins these responses only by scenario ID and year for display. It does not recompute aggregates or deltas.

## State and Failure Rules

- Scenario lifecycle is unchanged; only `completed` scenarios are accepted.
- Missing annual metric rows remain absent, not coerced to zero by the UI.
- Missing `run_metadata` yields unavailable provenance and a successful response.
- All database connections use read-only mode and close via a context/finally path.
- No entity in this document has a persistence transition.
