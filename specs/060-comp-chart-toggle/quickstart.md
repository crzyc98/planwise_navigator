# Quickstart: 060-comp-chart-toggle

**Feature**: Compensation Chart Toggle (Average/Total) with CAGR
**Scope**: Frontend-only (single file modification)

## What to Build

Add a toggle to the "Average Compensation - All Employees" chart in `AnalyticsDashboard.tsx` that:
1. Switches between average and total compensation views
2. Shows the CAGR percentage in the chart title

## Key File

- `planalign_studio/components/AnalyticsDashboard.tsx` — lines 504-528 (the compensation chart card)

## Available Data (Already in API Response)

The `workforce_progression` array already contains:
- `avg_compensation` — used today
- `total_compensation` — available but unused

The `cagr_metrics` array already contains:
- `{ metric: "Average Compensation", cagr_pct: X.XX }`
- `{ metric: "Total Compensation", cagr_pct: X.XX }`

**No backend changes required.**

## Implementation Steps

1. Add `compMetric` state variable (`'average' | 'total'`, default `'average'`)
2. Extend `workforceChartData` transform to include `totalCompensation` (in $M)
3. Add segmented toggle button next to chart title
4. Make chart title dynamic with CAGR from `cagr_metrics`
5. Switch `dataKey`, Y-axis formatter, tooltip formatter, and legend based on toggle state

## Verify

```bash
# Start frontend dev server
cd planalign_studio && npm run dev

# Navigate to Analytics page, select a completed simulation
# Verify:
# - Toggle appears next to chart title
# - Switching toggle updates chart data, Y-axis, tooltips
# - CAGR appears in title and updates with toggle
# - Single-year simulations show no CAGR
```
