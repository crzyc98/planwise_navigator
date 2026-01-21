# Data Model: Fix Mid-Year Termination Tenure Calculation

**Feature**: 023-fix-midyear-tenure
**Date**: 2026-01-21

## Affected Entities

### 1. Workforce Snapshot (`fct_workforce_snapshot`)

The primary output table containing employee state at year-end.

**Affected Fields**:

| Field | Type | Current Behavior | Fixed Behavior |
|-------|------|------------------|----------------|
| `current_tenure` | INTEGER | For terminated employees: may use pre-recalculated value from previous year (+1 increment) | Always: `floor((termination_date - hire_date) / 365.25)` for terminated employees |
| `tenure_band` | VARCHAR | Calculated from `fwc.current_tenure` (pre-recalculated value) | Calculated from recalculated `current_tenure` |

**Validation Rules**:
- `current_tenure >= 0` (non-negative)
- If `employment_status = 'terminated'` AND `termination_date IS NOT NULL`: tenure = `floor((termination_date - hire_date) / 365.25)`
- `tenure_band` must match `current_tenure` per band boundaries

### 2. New Hires (Intermediate CTE in `fct_workforce_snapshot`)

Employees hired in the current simulation year.

**Affected Fields**:

| Field | Type | Current Behavior | Fixed Behavior |
|-------|------|------------------|----------------|
| `current_tenure` | INTEGER | Hardcoded to 0 | Calculated: `floor((termination_date - hire_date) / 365.25)` when terminated, otherwise 0 |

### 3. Previous Year Snapshot (`int_active_employees_prev_year_snapshot`)

Helper model for year-over-year state transitions.

**No Changes Needed** - The +1 increment is correct for this model; the fix is in downstream consumption.

## Tenure Band Definitions

| Band Label | Min (inclusive) | Max (exclusive) |
|------------|-----------------|-----------------|
| `< 2` | 0 | 2 |
| `2-4` | 2 | 5 |
| `5-9` | 5 | 10 |
| `10-19` | 10 | 20 |
| `20+` | 20 | ∞ |

**Source**: `dbt/macros/bands/assign_tenure_band.sql`

## State Transitions

### Employee Tenure State Machine

```
[Census/Baseline]
    │
    ├──> Year 1: tenure = floor((2025-12-31 - hire_date) / 365.25)
    │
    └──> Year 2+: tenure = previous_year_tenure + 1 (if active at year start)
              │
              ├──> If terminated mid-year:
              │    tenure = floor((termination_date - hire_date) / 365.25)
              │    (OVERRIDE the +1 increment)
              │
              └──> If active at year-end:
                   tenure = floor((year_end - hire_date) / 365.25)
                   (Should match previous + 1)
```

### New Hire Tenure State Machine

```
[Hired in Year N]
    │
    ├──> If terminated in Year N:
    │    tenure = floor((termination_date - hire_date) / 365.25)
    │
    └──> If active at Year N end:
         tenure = 0 (less than 1 full year)
```

## Data Dependencies

```
fct_yearly_events (termination events)
         │
         └──> fct_workforce_snapshot.termination_date
                      │
                      └──> current_tenure calculation
                                  │
                                  └──> tenure_band derivation
```

## Parity Requirements

Both SQL and Polars pipelines must produce identical values for:

| Field | Tolerance |
|-------|-----------|
| `current_tenure` | Exact match (0 difference) |
| `tenure_band` | Exact match (string equality) |

**Test Query**:
```sql
SELECT
    employee_id,
    sql.current_tenure AS sql_tenure,
    polars.current_tenure AS polars_tenure,
    sql.tenure_band AS sql_band,
    polars.tenure_band AS polars_band
FROM sql_snapshot sql
JOIN polars_snapshot polars USING (employee_id, simulation_year)
WHERE sql.current_tenure != polars.current_tenure
   OR sql.tenure_band != polars.tenure_band
```
