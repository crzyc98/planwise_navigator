# Data Model: Fix Census Compensation Annualization Logic

**Feature Branch**: `043-fix-annualization-logic`
**Date**: 2026-02-10

## Entities

### Census Employee Record (Source: parquet)

| Field | Type | Description |
| ----- | ---- | ----------- |
| employee_id | VARCHAR | Unique employee identifier |
| employee_gross_compensation | DECIMAL(12,2) | Annual salary rate per data contract |
| employee_hire_date | DATE | Original hire date |
| employee_termination_date | DATE | Termination date (NULL if active) |

### Staged Census Record (Model: stg_census_data)

| Field | Type | Description | Derivation |
| ----- | ---- | ----------- | ---------- |
| employee_gross_compensation | DOUBLE | Raw annual rate from source | Passthrough |
| employee_annualized_compensation | DOUBLE | Full-year equivalent salary rate | = employee_gross_compensation (annual rate per contract) |
| employee_plan_year_compensation | DOUBLE | Prorated compensation for active days in plan year | = employee_gross_compensation * (days_active_in_year / 365.0) |
| days_active_in_year | INTEGER | Days active within plan year boundaries | Computed from hire/termination dates vs plan year boundaries |

**Validation Rules**:
- `employee_annualized_compensation` = `employee_gross_compensation` (always, per data contract)
- `employee_plan_year_compensation` <= `employee_gross_compensation * (366.0 / 365.0)` (leap year allowance)
- `employee_plan_year_compensation` >= 0
- `days_active_in_year` >= 0 and <= 366

### Baseline Workforce Record (Model: int_baseline_workforce)

| Field | Type | Description | Derivation |
| ----- | ---- | ----------- | ---------- |
| current_compensation | DOUBLE | Annual salary rate for simulation | = stg_census_data.employee_annualized_compensation |

**Validation Rules**:
- `current_compensation` = source `employee_annualized_compensation` (no transformation)

## Relationships

```
Census Parquet (employee_gross_compensation)
    ↓ [loaded by stg_census_data]
Staged Census Record
    ├── employee_annualized_compensation (= gross, annual rate)
    └── employee_plan_year_compensation (= gross * days/365)
    ↓ [consumed by int_baseline_workforce]
Baseline Workforce Record
    └── current_compensation (= employee_annualized_compensation)
    ↓ [consumed by 52 downstream models]
    ├── int_employee_compensation_by_year
    ├── int_merit_events (% applied to comp)
    ├── int_termination_events (final comp)
    ├── int_employee_contributions (proration ratio)
    └── fct_workforce_snapshot (carries to Year N+1)
```

## State Transitions

No state transitions apply — this is a data transformation fix, not a state machine change. The compensation values flow unidirectionally from census through staging to baseline to downstream models.

## Changes Required

| Model | Current Behavior | Target Behavior | Value Impact |
| ----- | --------------- | --------------- | ------------ |
| stg_census_data | `employee_annualized_compensation = employee_gross_compensation` with misleading comment | Same computation, clarified comments | None (values unchanged) |
| int_baseline_workforce | `current_compensation = stg.employee_annualized_compensation` | Same computation, HOTFIX comments removed | None (values unchanged) |
| New: test_annualization_logic.sql | N/A | Validates proration math and cross-model consistency | N/A (test only) |
