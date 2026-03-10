# Research: Trended Contribution Percentage Rates

**Feature**: 066-dc-contribution-rates
**Date**: 2026-03-09

## R1: Existing Rate Computation Pattern

**Decision**: Follow the exact `employer_cost_rate` computation pattern already in `analytics_service.py`

**Rationale**: The `_get_contribution_by_year()` method (line ~237-262) already:
1. Queries `fct_workforce_snapshot` for `total_compensation` via `SUM(prorated_annual_compensation)`
2. Computes `employer_cost_rate = (total_employer_cost / total_compensation * 100) if total_compensation > 0 else 0.0`
3. Rounds to 2 decimal places

The four new rates use identical logic with different numerators:
- `employee_contribution_rate`: `total_employee / total_compensation * 100`
- `match_contribution_rate`: `total_match / total_compensation * 100`
- `core_contribution_rate`: `total_core / total_compensation * 100`
- `total_contribution_rate`: sum of the above three

**Alternatives considered**:
- Per-employee average rates (rejected: spec requires aggregate plan-level rates)
- SQL-level computation (rejected: existing pattern computes in Python post-processing, simpler to extend)

## R2: Frontend Chart Pattern

**Decision**: Use `buildTrendData()` utility + Recharts `LineChart` — same pattern as Employer Cost Rate Trends chart

**Rationale**: `DCPlanComparisonSection.tsx` already has a `buildTrendData(fieldName, multiplier?)` function that:
1. Iterates scenarios and their `contribution_by_year` arrays
2. Builds `TrendDataPoint[]` with `{ year, [scenarioName]: value }`
3. Feeds directly into `<LineChart>` with per-scenario `<Line>` components

For multi-series (4 rates in one chart), the pattern differs slightly — need to build data with 4 series per data point rather than 1. The contribution breakdown bar chart already demonstrates multi-series rendering.

**Alternatives considered**:
- Stacked area chart (rejected: line chart matches existing trend charts for consistency)
- Separate charts per rate (rejected: spec calls for one chart with 4 series for comparison)

## R3: Zero-Compensation Edge Case

**Decision**: Return 0.0 for all rates when `total_compensation == 0`

**Rationale**: Existing `employer_cost_rate` already uses this guard: `if total_compensation > 0 else 0.0`. Apply same guard to all four new rates. This handles:
- All employees terminated in a year
- Empty simulation years
- No active workforce

**Alternatives considered**:
- Return `null`/`None` (rejected: would require nullable fields in Pydantic model and null handling in charts)
- Skip the year (rejected: would create gaps in trend lines)

## R4: Grand Totals Extension

**Decision**: Extend `_compute_grand_totals()` to include the four new aggregate rates

**Rationale**: The method (line ~36-70) already sums `total_employer_cost` and `total_compensation` across years and computes `employer_cost_rate`. Same pattern for the new rates using cross-year totals.

## R5: TypeScript Interface Extension

**Decision**: Add 4 new fields to `ContributionYearSummary` interface in `api.ts`

**Rationale**: TypeScript interface must match the Pydantic model. Adding fields with `number` type maintains consistency. Existing consumers won't break since new fields are additive.

## R6: Summary Table Integration

**Decision**: Add 4 new rows to the `SummaryMetricRow[]` array in the summary comparison table

**Rationale**: The summary table already has rows for Participation Rate, Avg Deferral Rate, Employer Cost Rate, and Total Contributions. Adding the 4 contribution rate rows follows the same `{ metric, unit, favorableDirection, values, deltas, deltaPcts }` pattern.

## No Unresolved Items

All technical decisions are clear. No NEEDS CLARIFICATION items remain.
