# Research: Compensation Chart Toggle with CAGR

**Feature**: 060-comp-chart-toggle
**Date**: 2026-03-03

## R1: Data Availability for Total Compensation

**Decision**: Use existing `total_compensation` field from `workforce_progression` API response — no backend changes needed.

**Rationale**: The `_query_workforce_progression()` function in `results_reader.py` (line 117) already queries `SUM(... prorated_annual_compensation ...) as total_compensation` and returns it in every workforce progression row. The frontend currently ignores this field, only using `avg_compensation` (line 226 of `AnalyticsDashboard.tsx`).

**Alternatives considered**:
- Derive total on frontend from `headcount * avg_compensation` — rejected because the backend already provides the exact figure from the SQL query, and deriving it would introduce rounding errors.
- Add a new API endpoint — rejected as unnecessary since the data is already present.

## R2: CAGR Data Source

**Decision**: Use existing `cagr_metrics` array from the API response, which already contains pre-computed CAGR for both "Average Compensation" and "Total Compensation".

**Rationale**: The `_compute_cagr_metrics()` function in `results_reader.py` (lines 263-285) already computes and returns three CAGR metrics:
1. "Total Headcount"
2. "Total Compensation" — `cagr_pct` for total comp
3. "Average Compensation" — `cagr_pct` for avg comp

The frontend can look up the appropriate CAGR by matching the `metric` field name based on the toggle state.

**Alternatives considered**:
- Calculate CAGR on the frontend from chart data — rejected because the backend already provides it with consistent rounding.
- Add a dedicated CAGR endpoint — rejected as unnecessary.

## R3: Toggle UI Pattern

**Decision**: Use a simple segmented button (two-option pill toggle) placed inline with the chart title.

**Rationale**: The existing codebase uses Tailwind CSS for all styling. A segmented button is the simplest toggle pattern that:
- Is visually clear (selected state is obvious)
- Matches the existing card/chart visual style
- Requires no additional dependencies
- Works well with exactly two options

**Alternatives considered**:
- Dropdown select — rejected as too heavy for a binary choice.
- Radio buttons — rejected as less visually polished for inline placement.
- Tab bar — rejected as it implies separate views rather than the same chart with different data.

## R4: Y-Axis Formatting for Total Compensation

**Decision**: Auto-detect scale based on max value: use `$K` for values under 1M, `$M` for values 1M+.

**Rationale**: Average compensation is typically $100K-$200K range (displayed as "$125K"), while total compensation for 1000+ employees could be $100M+ (should display as "$125M"). The formatter needs to adapt dynamically.

**Alternatives considered**:
- Always use `$M` for total — rejected because small organizations might have total comp under $1M.
- Use raw numbers — rejected as unreadable for large values.
