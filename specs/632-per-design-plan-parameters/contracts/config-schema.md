# Configuration Contract: Per-Design Parameters

## Top-level shape

`plan_design_parameters` is optional. When absent, the current scalar export and SQL paths are authoritative and unchanged. When present, its keys must exactly equal `get_plan_design_set()`.

```yaml
plan_design_assignment:
  default_plan_design_id: legacy_design
  rules:
    - type: hire_date_cutoff
      cutoff: 2025-01-01
      plan_design_id: current_design

# All designs share the global formula-family selectors elsewhere in config.
plan_design_parameters:
  legacy_design:
    match:
      cap_percent: 0.03
      tiers:
        - employee_min: 0.00
          employee_max: 0.03
          match_rate: 1.00
    employer_core:
      contribution_rate: 0.02
      graded_schedule: []
    auto_enrollment:
      default_deferral_rate: 0.03
      window_days: 45
      scope: all_eligible_employees
    deferral_escalation:
      increment: 0.01
      cap: 0.10
    eligibility:
      waiting_period_days: 0

  current_design:
    match:
      cap_percent: 0.03
      tiers:
        - employee_min: 0.00
          employee_max: 0.06
          match_rate: 0.50
    employer_core:
      contribution_rate: 0.03
      graded_schedule: []
    auto_enrollment:
      default_deferral_rate: 0.06
      window_days: 30
      scope: new_hires_only
    deferral_escalation:
      increment: 0.02
      cap: 0.08
    eligibility:
      waiting_period_days: 90
```

## Validation rules

- Map keys are nonblank plan design ids accepted by the assignment configuration.
- Map keys exactly equal the assignment design set; the validation error lists missing and extra ids.
- Every section shown above is required in keyed mode. Family-inapplicable schedule arrays may be empty.
- Percent/rate fields are decimal fractions in `[0, 1]`.
- Days are nonnegative integers.
- Scopes are `all_eligible_employees` or `new_hires_only`.
- Tier and service-band intervals use `[min, max)` semantics, are ordered, nonoverlapping, and unique within a design.
- A formula-specific schedule must match the one global family selector. No design may select its own family in Tier 1.
- Configuration export sorts map keys and schedule rows deterministically.
- No SQL consumer substitutes another design's parameters when keyed mode is active.

## Runtime relation contract

`get_plan_design_parameters` returns exactly one row per configured design:

| Column | SQL type |
|---|---|
| `plan_design_id` | `VARCHAR` |
| `match_cap_percent` | `DECIMAL(10,6)` |
| `employer_core_contribution_rate` | `DECIMAL(10,6)` |
| `auto_enrollment_default_deferral_rate` | `DECIMAL(10,6)` |
| `auto_enrollment_window_days` | `INTEGER` |
| `auto_enrollment_scope` | `VARCHAR` |
| `deferral_escalation_increment` | `DECIMAL(10,6)` |
| `deferral_escalation_cap` | `DECIMAL(10,6)` |
| `eligibility_waiting_period_days` | `INTEGER` |

Repeated match/core macros return `plan_design_id`, an explicit ordinal, typed interval bounds, and typed rates. With no input, every macro returns the same columns and types with zero rows via `WHERE FALSE`.
