# Data Model: DC Plan Comparison Charts

**Feature Branch**: `057-dc-comparison-charts`
**Date**: 2026-02-21

## Existing Entities (No Changes Required)

### ContributionYearSummary (Backend → Frontend)

Per-scenario, per-year aggregate metrics. Already defined in `api.ts`.

| Field | Type | Description |
|-------|------|-------------|
| year | number | Simulation year |
| total_employee_contributions | number | Employee deferral dollar amount |
| total_employer_match | number | Employer match dollar amount |
| total_employer_core | number | Employer core contribution dollar amount |
| total_all_contributions | number | Sum of all contributions |
| participant_count | number | Count of enrolled employees |
| average_deferral_rate | number | Average deferral rate (decimal) |
| participation_rate | number | Participation rate (0-100%) |
| total_employer_cost | number | Match + core total |
| total_compensation | number | Total compensation base |
| employer_cost_rate | number | Employer cost as % of compensation |

### DCPlanAnalytics (Backend → Frontend)

Per-scenario aggregate with year-by-year breakdown. Already defined in `api.ts`.

| Field | Type | Description |
|-------|------|-------------|
| scenario_id | string | Unique scenario identifier |
| scenario_name | string | Display name |
| contribution_by_year | ContributionYearSummary[] | Year-by-year metrics array |
| participation_rate | number | Overall participation rate |
| average_deferral_rate | number | Weighted average deferral rate |
| employer_cost_rate | number | Overall employer cost rate |
| total_employee_contributions | number | Grand total employee contributions |
| total_employer_match | number | Grand total employer match |
| total_employer_core | number | Grand total employer core |

### DCPlanComparisonResponse (Backend → Frontend)

Multi-scenario comparison envelope. Already defined in `api.ts`.

| Field | Type | Description |
|-------|------|-------------|
| scenarios | string[] | Scenario IDs in comparison |
| scenario_names | Record<string, string> | ID → display name mapping |
| analytics | DCPlanAnalytics[] | One analytics object per scenario |

## New Frontend-Only Types (Derived for Chart Rendering)

### TrendChartDataPoint

Recharts-compatible data point for line charts. One per simulation year.

| Field | Type | Description |
|-------|------|-------------|
| year | number | Simulation year (x-axis) |
| [scenarioName] | number \| undefined | Metric value for that scenario (dynamic key) |

**Example**:
```
{ year: 2025, "Baseline": 2.83, "Enhanced Match": 3.15 }
{ year: 2026, "Baseline": 2.91, "Enhanced Match": 3.22 }
```

### ContributionBreakdownDataPoint

Recharts-compatible data point for grouped bar chart. One per scenario.

| Field | Type | Description |
|-------|------|-------------|
| name | string | Scenario display name |
| employee | number | Employee contribution amount |
| match | number | Employer match amount |
| core | number | Employer core amount |
| fill | string | Scenario color |

### SummaryMetricRow

Row in the summary comparison table.

| Field | Type | Description |
|-------|------|-------------|
| metric | string | Metric label (e.g., "Participation Rate") |
| unit | "percent" \| "currency" | Display format |
| favorableDirection | "higher" \| "lower" | Which direction is "green" |
| values | Record<string, number> | scenario name → value |
| deltas | Record<string, number> | scenario name → delta from baseline |
| deltaPcts | Record<string, number> | scenario name → delta percentage |

## Data Flow

```
API Call: compareDCPlanAnalytics(workspaceId, scenarioIds)
  │
  ▼
DCPlanComparisonResponse
  │
  ├─► Transform to TrendChartDataPoint[]  ──► Line Charts (3x)
  │     (one array per metric: employer_cost_rate,
  │      participation_rate, average_deferral_rate)
  │
  ├─► Transform to ContributionBreakdownDataPoint[] ──► Grouped Bar Chart
  │     (extract final year's contribution data)
  │
  └─► Transform to SummaryMetricRow[] ──► Summary Table
        (compute deltas from first scenario as baseline)
```

## Validation Rules

- `participation_rate` must be 0-100 (percentage, not decimal)
- `average_deferral_rate` is a decimal (e.g., 0.06 = 6%) — must multiply by 100 for display
- `employer_cost_rate` is already a percentage (e.g., 2.83 = 2.83%)
- Currency values may be zero but never negative
- `year` must be a positive integer
