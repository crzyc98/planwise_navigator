# Data Model: DC Plan Metrics in Scenario Comparison

**Feature**: 048-comparison-dc-metrics
**Date**: 2026-02-12

## New Entities

### DCPlanMetrics

Aggregated DC plan metrics for a single scenario in a single simulation year. Mirrors the structure of `WorkforceMetrics` for API consistency.

| Field | Type | Description | Derivation |
| ----- | ---- | ----------- | ---------- |
| `participation_rate` | float | % of active employees enrolled | `COUNT(active+enrolled) / COUNT(active) * 100` |
| `avg_deferral_rate` | float | Mean deferral rate among enrolled | `AVG(current_deferral_rate WHERE is_enrolled_flag)` |
| `total_employee_contributions` | float | Sum of employee contributions | `SUM(prorated_annual_contributions)` |
| `total_employer_match` | float | Sum of employer match amounts | `SUM(employer_match_amount)` |
| `total_employer_core` | float | Sum of employer core amounts | `SUM(employer_core_amount)` |
| `total_employer_cost` | float | Match + core combined | `total_employer_match + total_employer_core` |
| `employer_cost_rate` | float | Employer cost as % of compensation | `total_employer_cost / total_compensation * 100` |
| `participant_count` | int | Number of enrolled employees | `COUNT(WHERE is_enrolled_flag)` |

**Zero-value defaults**: All fields default to 0.0 (or 0 for int) when no data is available. Division-by-zero scenarios (zero active employees, zero compensation) return 0.

### DCPlanComparisonYear

Year-level comparison container with per-scenario values and deltas. Follows the `WorkforceComparisonYear` pattern.

| Field | Type | Description |
| ----- | ---- | ----------- |
| `year` | int | Simulation year |
| `values` | Dict[str, DCPlanMetrics] | Raw metrics keyed by scenario_id |
| `deltas` | Dict[str, DCPlanMetrics] | Delta from baseline keyed by scenario_id |

**Delta calculation**: For each non-baseline scenario, `delta = scenario_value - baseline_value`. Baseline deltas are always zero.

## Modified Entities

### ComparisonResponse (extended)

| Field | Type | Change |
| ----- | ---- | ------ |
| `dc_plan_comparison` | List[DCPlanComparisonYear] | **ADDED** - Year-by-year DC plan comparison |

All existing fields (`scenarios`, `scenario_names`, `baseline_scenario`, `workforce_comparison`, `event_comparison`, `summary_deltas`) remain unchanged.

### summary_deltas (extended keys)

Two new entries added to the existing `summary_deltas: Dict[str, DeltaValue]`:

| Key | Description |
| --- | ----------- |
| `final_participation_rate` | Participation rate from the final simulation year |
| `final_employer_cost` | Total employer cost from the final simulation year |

Both use the existing `DeltaValue` model (baseline, scenarios, deltas, delta_pcts).

## Data Source

All metrics are derived from `fct_workforce_snapshot` via a single GROUP BY query per scenario database:

```sql
SELECT
    simulation_year,
    COALESCE(COUNT(CASE WHEN UPPER(employment_status) = 'ACTIVE' AND is_enrolled_flag THEN 1 END) * 100.0
        / NULLIF(COUNT(CASE WHEN UPPER(employment_status) = 'ACTIVE' THEN 1 END), 0), 0) AS participation_rate,
    AVG(CASE WHEN is_enrolled_flag THEN current_deferral_rate ELSE NULL END) AS avg_deferral_rate,
    COALESCE(SUM(prorated_annual_contributions), 0) AS total_employee_contributions,
    COALESCE(SUM(employer_match_amount), 0) AS total_employer_match,
    COALESCE(SUM(employer_core_amount), 0) AS total_employer_core,
    COALESCE(SUM(employer_match_amount) + SUM(employer_core_amount), 0) AS total_employer_cost,
    COALESCE(SUM(prorated_annual_compensation), 0) AS total_compensation,
    COUNT(CASE WHEN is_enrolled_flag THEN 1 END) AS participant_count
FROM fct_workforce_snapshot
GROUP BY simulation_year
ORDER BY simulation_year
```

**Note**: `employer_cost_rate` is computed in Python as `total_employer_cost / total_compensation * 100` (with zero-check) since it requires the intermediate `total_compensation` value.

## Relationships

```
ComparisonResponse
├── workforce_comparison: List[WorkforceComparisonYear]  (existing)
├── event_comparison: List[EventComparisonMetric]         (existing)
├── dc_plan_comparison: List[DCPlanComparisonYear]        (NEW)
│   └── values/deltas: Dict[str, DCPlanMetrics]           (NEW)
└── summary_deltas: Dict[str, DeltaValue]                 (extended with 2 new keys)
```
