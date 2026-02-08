# Data Model: Fix Census Compensation Annualization Logic

**Branch**: `037-fix-annualization-logic` | **Date**: 2026-02-07

## Entities

### Staged Census Record (`stg_census_data`)

The staging model cleans and enriches raw census parquet data. The compensation fields are:

| Field | Type | Source | Description |
| ----- | ---- | ------ | ----------- |
| `employee_gross_compensation` | DECIMAL(12,2) | Raw parquet | Annual salary rate as reported in census |
| `employee_annualized_compensation` | DOUBLE | Computed | Full-year equivalent rate. **After fix**: equals `employee_gross_compensation` directly |
| `employee_plan_year_compensation` | DOUBLE | Computed | Pro-rated compensation for days active in plan year: `gross * days_active / 365` |
| `days_active_in_year` | INTEGER | Computed | Days employee was active during the plan year (0 to 365/366) |

**Relationships**:
- Source: `read_parquet(census_parquet_path)`
- Consumer: `int_baseline_workforce` (reads `employee_annualized_compensation` after fix)

**Validation Rules**:
- `employee_annualized_compensation` = `employee_gross_compensation` for all rows (by definition, since gross is already annual)
- `employee_plan_year_compensation` <= `employee_gross_compensation` (pro-rated can't exceed annual)
- `employee_plan_year_compensation` >= 0
- When `days_active_in_year` = 0, `employee_annualized_compensation` = `employee_gross_compensation`

### Baseline Workforce Record (`int_baseline_workforce`)

The baseline model prepares simulation-ready employee records from staging data.

| Field | Type | Source | Description |
| ----- | ---- | ------ | ----------- |
| `current_compensation` | DOUBLE | `stg_census_data.employee_annualized_compensation` | Primary salary field for all downstream models. **After fix**: sourced from annualized field instead of gross |

**Relationships**:
- Source: `stg_census_data` (via `ref('stg_census_data')`)
- Consumers: `int_employee_compensation_by_year`, `fct_workforce_snapshot`, `int_workforce_needs`, and 25+ downstream models

**State Transitions**: None (static baseline record, no lifecycle changes within this model)

## Change Summary

### Before Fix
```
stg_census_data:
  employee_annualized_compensation = (gross * days/365) * 365/days  [no-op formula]
  employee_plan_year_compensation = gross * days/365                [correct pro-rating]

int_baseline_workforce:
  current_compensation = stg.employee_gross_compensation            [HOTFIX bypass]
```

### After Fix
```
stg_census_data:
  employee_annualized_compensation = employee_gross_compensation    [direct assignment]
  employee_plan_year_compensation = gross * days/365                [unchanged]

int_baseline_workforce:
  current_compensation = stg.employee_annualized_compensation       [canonical path]
```

### Value Impact
For all rows: `employee_gross_compensation` = `employee_annualized_compensation` both before and after. The downstream `current_compensation` values are **numerically identical**. This is a code clarity fix, not a data change.
