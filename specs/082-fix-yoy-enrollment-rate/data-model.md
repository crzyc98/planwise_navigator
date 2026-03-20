# Data Model: Fix Year-over-Year Voluntary Enrollment Rate Override

**Date**: 2026-03-20
**Branch**: `082-fix-yoy-enrollment-rate`

## Entities (No Changes)

This bug fix does not modify any data model entities, schemas, or relationships. The change is limited to how an existing configuration variable (`voluntary_enrollment_rate`) is applied within an existing SQL computation.

## Existing Entities (Reference)

### Enrollment Event (unchanged)
- **Table**: `int_enrollment_events` / `fct_yearly_events`
- **Key fields**: `employee_id`, `scenario_id`, `plan_design_id`, `simulation_year`, `event_type`, `enrollment_source`
- **Enrollment sources**: `auto_enrollment`, `voluntary_enrollment`, `proactive_voluntary`, `year_over_year_conversion`
- No schema changes — the `year_over_year_conversion` source already exists

### Voluntary Enrollment Rate (unchanged)
- **dbt variable**: `voluntary_enrollment_rate`
- **Type**: float (0.0–1.0)
- **Default**: 1.0
- **Sources**: `dbt_project.yml`, `simulation_config.yaml`, PlanAlign Studio UI
- No new variables or configuration fields

## State Transitions (unchanged)

```
Non-Enrolled → [year-over-year conversion] → Enrolled (voluntary)
```

The transition logic is unchanged. The only difference is that the conversion **probability** is now scaled by `voluntary_enrollment_rate`, which can reduce it to zero.

## Impact Analysis

| Component | Changed? | Notes |
|-----------|----------|-------|
| Event schema | No | No new fields or event types |
| Config model (Pydantic) | No | `voluntary_enrollment_rate` already exists |
| Config export (Python) | No | Already exports `voluntary_enrollment_rate` to dbt |
| dbt variables | No | `voluntary_enrollment_rate` already defined in `dbt_project.yml` |
| SQL probability calculation | **Yes** | One additional multiplier in year-over-year CTE |
| Downstream models | No | Consume enrollment events regardless of source probability |
