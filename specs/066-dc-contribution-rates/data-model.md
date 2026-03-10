# Data Model: Trended Contribution Percentage Rates

**Feature**: 066-dc-contribution-rates
**Date**: 2026-03-09

## Entity Changes

### ContributionYearSummary (Extended)

**Location**: `planalign_api/models/analytics.py`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `year` | int | required | Simulation year |
| `total_employee_contributions` | float | required | Total employee deferrals ($) |
| `total_employer_match` | float | required | Total employer match ($) |
| `total_employer_core` | float | required | Total employer core ($) |
| `total_all_contributions` | float | required | Total all contributions ($) |
| `participant_count` | int | required | Enrolled participant count |
| `average_deferral_rate` | float | 0.0 | Average deferral rate |
| `participation_rate` | float | 0.0 | Participation rate (0-100%) |
| `total_employer_cost` | float | 0.0 | Match + core total ($) |
| `total_compensation` | float | 0.0 | Total prorated compensation ($) |
| `employer_cost_rate` | float | 0.0 | Employer cost / compensation (%) |
| **`employee_contribution_rate`** | **float** | **0.0** | **NEW: Employee deferrals / compensation (%)** |
| **`match_contribution_rate`** | **float** | **0.0** | **NEW: Employer match / compensation (%)** |
| **`core_contribution_rate`** | **float** | **0.0** | **NEW: Employer core / compensation (%)** |
| **`total_contribution_rate`** | **float** | **0.0** | **NEW: All contributions / compensation (%)** |

### DCPlanAnalytics (Extended)

**Location**: `planalign_api/models/analytics.py`

Add aggregate-level rates (same 4 fields) computed across all years in `_compute_grand_totals()`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| **`employee_contribution_rate`** | **float** | **0.0** | **NEW: Aggregate employee rate (%)** |
| **`match_contribution_rate`** | **float** | **0.0** | **NEW: Aggregate match rate (%)** |
| **`core_contribution_rate`** | **float** | **0.0** | **NEW: Aggregate core rate (%)** |
| **`total_contribution_rate`** | **float** | **0.0** | **NEW: Aggregate total rate (%)** |

## Computation Rules

### Per-Year Rate Computation

```
employee_contribution_rate = (total_employee_contributions / total_compensation) * 100
match_contribution_rate    = (total_employer_match / total_compensation) * 100
core_contribution_rate     = (total_employer_core / total_compensation) * 100
total_contribution_rate    = employee_contribution_rate + match_contribution_rate + core_contribution_rate
```

**Guard**: If `total_compensation == 0`, all rates = 0.0
**Rounding**: 2 decimal places (consistent with `employer_cost_rate`)

### Aggregate Rate Computation

```
aggregate_rate = (sum_all_years_numerator / sum_all_years_total_compensation) * 100
```

Computed from cross-year totals, not averages of per-year rates.

## Data Source

All fields derived from `fct_workforce_snapshot`:
- `prorated_annual_compensation` → denominator
- `prorated_annual_contributions` → employee deferrals numerator
- `employer_match_amount` → match numerator
- `employer_core_amount` → core numerator

No new database tables, columns, or dbt models required.

## Validation Rules

- All rates must be non-negative (0.0 minimum)
- `total_contribution_rate` must equal `employee_contribution_rate + match_contribution_rate + core_contribution_rate` (within floating-point tolerance)
- Rates are percentages (typically 0-30% range, but no upper bound enforced)
