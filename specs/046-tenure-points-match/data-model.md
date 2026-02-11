# Data Model: Tenure-Based and Points-Based Employer Match Modes

**Feature Branch**: `046-tenure-points-match`
**Date**: 2026-02-11

## Entities

### TenureMatchTier

A configuration entity defining a match rate bracket based on employee years of service.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| min_years | integer | >= 0, required | Lower bound of service years (inclusive) |
| max_years | integer or null | > min_years or null | Upper bound of service years (exclusive); null = unbounded |
| match_rate | decimal | 0-100, required | Match rate as percentage (e.g., 50 = 50%) |
| max_deferral_pct | decimal | 0-100, required | Maximum employee deferral % eligible for match (e.g., 6 = 6%) |

**Validation rules**:
- First tier must have `min_years = 0`
- Last tier is recommended to have `max_years = null` (unbounded). If the last tier has a finite max, employees exceeding that value receive no match (default rate = 0).
- Tiers must be contiguous: tier[N].max_years == tier[N+1].min_years
- No gaps or overlaps between tiers
- At least one tier required when `employer_match_status = 'tenure_based'`

### PointsMatchTier

A configuration entity defining a match rate bracket based on employee age+tenure points.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| min_points | integer | >= 0, required | Lower bound of points (inclusive) |
| max_points | integer or null | > min_points or null | Upper bound of points (exclusive); null = unbounded |
| match_rate | decimal | 0-100, required | Match rate as percentage (e.g., 50 = 50%) |
| max_deferral_pct | decimal | 0-100, required | Maximum employee deferral % eligible for match (e.g., 6 = 6%) |

**Validation rules**: Same contiguity rules as TenureMatchTier.

### EmployeePoints (Computed)

A per-employee, per-year computed value used for points-based tier assignment. Not stored as a separate entity — computed inline in the match calculation model.

| Field | Type | Description |
|-------|------|-------------|
| employee_id | string | Employee identifier |
| simulation_year | integer | Year of calculation |
| current_age | decimal | Employee age in the simulation year |
| years_of_service | integer | FLOOR(current_tenure) |
| applied_points | integer | FLOOR(current_age) + FLOOR(years_of_service) |

### MatchCalculationResult (Extended)

Existing entity extended with new fields for tenure-based and points-based modes.

**New output columns**:

| Field | Type | Populated When | Description |
|-------|------|----------------|-------------|
| applied_points | integer or null | `points_based` mode | Employee's calculated points value (FLOOR(age) + FLOOR(tenure)) |
| formula_type | string | All modes | Extended to include `'tenure_based'` and `'points_based'` values |

**Existing output columns** (unchanged):

| Field | Type | Description |
|-------|------|-------------|
| employer_match_amount | decimal | Final match after eligibility and caps |
| uncapped_match_amount | decimal | Match before caps |
| capped_match_amount | decimal | Match after caps, before eligibility |
| applied_years_of_service | integer or null | Populated for `graded_by_service` and `tenure_based` modes |
| formula_type | string | `'deferral_based'`, `'graded_by_service'`, `'tenure_based'`, or `'points_based'` |
| match_status | string | `'ineligible'`, `'no_deferrals'`, or `'calculated'` |
| is_eligible_for_match | boolean | From eligibility model |
| match_eligibility_reason | string | Reason code for eligibility determination |
| match_cap_applied | boolean | Whether match cap was enforced |

## State Transitions

```
Configuration Load → Pydantic Validation → dbt Variable Export → Model Compilation → Match Calculation
```

1. **Configuration Load**: YAML or API provides `employer_match_status` + tier arrays
2. **Pydantic Validation**: `TenureMatchTier`/`PointsMatchTier` models validate contiguity
3. **dbt Variable Export**: `_export_employer_match_vars()` transforms field names and exports to dbt
4. **Model Compilation**: Jinja conditional selects calculation branch based on `employer_match_status`
5. **Match Calculation**: SQL computes match per employee using tier lookup macros

## Relationships

```
EmployerMatchSettings
├── employer_match_status: enum (deferral_based | graded_by_service | tenure_based | points_based)
├── tenure_match_tiers: TenureMatchTier[] (used when status = tenure_based)
├── points_match_tiers: PointsMatchTier[] (used when status = points_based)
├── employer_match_graded_schedule: GradedScheduleTier[] (existing, used when status = graded_by_service)
└── formulas: Dict (existing, used when status = deferral_based)

int_employee_match_calculations
├── joins int_employee_contributions (provides current_age, deferral_rate, compensation)
├── joins int_workforce_snapshot_optimized (provides current_tenure → years_of_service)
├── joins int_employer_eligibility (provides is_eligible_for_match)
└── outputs MatchCalculationResult (with applied_points for points_based mode)
```
