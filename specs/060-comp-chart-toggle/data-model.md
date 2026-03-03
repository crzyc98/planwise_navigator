# Data Model: Compensation Chart Toggle with CAGR

**Feature**: 060-comp-chart-toggle
**Date**: 2026-03-03

## Existing Entities (No Changes Required)

### Workforce Progression (API Response)

Already returned by `GET /api/scenarios/{scenarioId}/results` in `workforce_progression` array:

| Field | Type | Description |
|-------|------|-------------|
| `simulation_year` | number | The simulation year |
| `headcount` | number | Active employee count |
| `avg_compensation` | number | Average compensation (all employees) |
| `total_compensation` | number | Sum of prorated annual compensation (active employees) |
| `active_avg_compensation` | number | Average compensation (active only) |

### CAGR Metrics (API Response)

Already returned in `cagr_metrics` array with three entries:

| Entry | metric | start_value | end_value | years | cagr_pct |
|-------|--------|-------------|-----------|-------|----------|
| 0 | "Total Headcount" | number | number | number | number |
| 1 | "Total Compensation" | number (dollars) | number (dollars) | number | number (%) |
| 2 | "Average Compensation" | number (dollars) | number (dollars) | number | number (%) |

## New Frontend State (Component-Level Only)

### CompensationMetricToggle State

| State Variable | Type | Default | Description |
|---------------|------|---------|-------------|
| `compMetric` | `'average' \| 'total'` | `'average'` | Currently selected compensation metric |

### Derived Chart Data

The existing `workforceChartData` transformation (line 223) will be extended to include:

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `avgCompensation` | number | `row.avg_compensation / 1000` | Average comp in $K (existing) |
| `totalCompensation` | number | `row.total_compensation / 1_000_000` | Total comp in $M |

### CAGR Lookup

| Toggle State | Lookup Key | Display Format |
|-------------|------------|----------------|
| `'average'` | `cagr_metrics.find(m => m.metric === "Average Compensation")` | `CAGR: X.X%` |
| `'total'` | `cagr_metrics.find(m => m.metric === "Total Compensation")` | `CAGR: X.X%` |

## State Transitions

```
Page Load → compMetric = 'average' (default)
  → Chart shows avgCompensation, Y-axis in $K, CAGR from "Average Compensation" metric

User clicks "Total" toggle
  → compMetric = 'total'
  → Chart shows totalCompensation, Y-axis in $M, CAGR from "Total Compensation" metric

User clicks "Average" toggle
  → compMetric = 'average'
  → Chart reverts to default view

Page refresh / navigation
  → compMetric resets to 'average'
```
